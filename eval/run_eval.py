"""Evaluation: compares three configurations on the VERIFIED questions in questions.json.

  A) vector-only retrieval + one LLM call
  B) hybrid + rerank retrieval + one LLM call
  C) full agent (tools, multi-step)

Run:  python -m eval.run_eval            (needs data/index built and LLM_* set in .env)

Every number written to results.* comes from this script. Nothing is hand-edited.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from app.agent import AgentResult, run_agent
from app.baseline import run_baseline
from app.config import Settings, get_settings, llm_kwargs
from app.retrieval import Retriever
from app.tools import ToolBox

CONFIGS = {
    "A": ("vector-only + 1 LLM call", "vector"),
    "B": ("hybrid+rerank + 1 LLM call", "hybrid_rerank"),
    "C": ("full agent", None),
}
CATEGORIES = ("lookup", "multi_step", "comparison", "unanswerable")
MANUAL_SAMPLE = 15

JUDGE_PROMPT = """You are a STRICT grader. You get a QUESTION, the EXPECTED answer and a \
MODEL answer. Mark correct=true only if the model answer states every key fact (names, \
numbers, years, directions of change) in the expected answer and contradicts none of it. \
Extra correct detail is fine. Vague, partial, hedged or wrong answers are correct=false. \
Judge only against the expected answer, not your own knowledge.
Reply with ONLY JSON: {"correct": true|false, "reason": "<one short sentence>"}"""


# ---------------------------------------------------------------- rate limiting
def throttled(
    completion: Callable[..., Any],
    rpm: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[..., Any]:
    """Wrap an LLM call so calls are at least 60/rpm seconds apart. Free API tiers allow only
    a few requests per minute; pacing ourselves is cheaper than failing and retrying."""
    if rpm <= 0:
        return completion
    interval, last, lock = 60.0 / rpm, [-1e18], threading.Lock()

    def wrapper(**kwargs: Any) -> Any:
        with lock:
            wait = last[0] + interval - clock()
            if wait > 0:
                sleep(wait)
            last[0] = clock()
        return completion(**kwargs)

    return wrapper


# ---------------------------------------------------------------- question schema
class ExpectedPage(BaseModel):
    company: str
    fiscal_year: int
    page: int

    @field_validator("company")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("fiscal_year", mode="before")
    @classmethod
    def _year(cls, v: Any) -> Any:
        return 2000 + v if isinstance(v, int) and 0 <= v < 100 else v


class Question(BaseModel):
    id: str
    category: Literal["lookup", "multi_step", "comparison", "unanswerable"]
    question: str
    expected_answer: str
    expected_pages: list[ExpectedPage] = []
    numeric: bool = False
    tolerance: float = 0.01  # RELATIVE: 0.01 = within 1% of the expected number
    verified: bool = False  # only questions a human checked against the PDF are scored

    @model_validator(mode="after")
    def _check(self) -> Question:
        if self.category != "unanswerable" and not self.expected_pages:
            raise ValueError(f"{self.id}: answerable questions need expected_pages")
        if self.numeric and extract_numbers(self.expected_answer) == []:
            raise ValueError(f"{self.id}: numeric question needs a number in expected_answer")
        return self


def load_questions(path: str | Path) -> list[Question]:
    qs = [Question.model_validate(d) for d in json.loads(Path(path).read_text("utf-8"))]
    ids = [q.id for q in qs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids in questions.json")
    return qs


# ---------------------------------------------------------------- scoring helpers
NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> list[float]:
    """'Rs 1,53,670 crore (up 4.7%)' -> [153670.0, 4.7]. Commas are thousands separators."""
    return [float(m.replace(",", "")) for m in NUM_RE.findall(text)]


def numeric_correct(answer: str, expected: str, tolerance: float) -> bool:
    """Correct if ANY number in the answer is within relative tolerance of the expected one.
    'Any' (not 'the first') because answers often mention several numbers; the trade-off is
    a small chance of a lucky match, which the manual re-check sample helps catch."""
    exp = extract_numbers(expected)[0]
    for got in extract_numbers(answer):
        if (abs(got - exp) <= tolerance * abs(exp)) if exp != 0 else (abs(got) <= tolerance):
            return True
    return False


def page_hit(retrieved: list[dict], expected: list[ExpectedPage]) -> bool:
    want = {(p.company, p.fiscal_year, p.page) for p in expected}
    return any((r["company"], r["fiscal_year"], r["page"]) in want for r in retrieved)


def judge(
    q: Question, answer: str, settings: Settings, completion: Callable[..., Any]
) -> tuple[bool, str]:
    resp = completion(
        model=settings.judge_model or settings.llm_model,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {
                "role": "user",
                "content": f"QUESTION: {q.question}\nEXPECTED: {q.expected_answer}\n"
                f"MODEL: {answer}",
            },
        ],
        temperature=0,
        **llm_kwargs(settings),
    )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.choices[0].message.content.strip())
    data = json.loads(text)
    return bool(data["correct"]), str(data.get("reason", ""))


# ---------------------------------------------------------------- running one question
def _evaluate_once(
    q: Question,
    config: str,
    retriever: Retriever,
    settings: Settings,
    completion: Callable[..., Any],
) -> dict:
    rec: dict[str, Any] = {
        "id": q.id, "category": q.category, "config": config, "question": q.question,
        "expected_answer": q.expected_answer, "judge_used": False, "error": None,
    }
    try:
        if config == "C":
            box = ToolBox(retriever, weak_threshold=settings.weak_score_threshold)
            res: AgentResult = run_agent(q.question, box, settings, completion)
        else:
            res = run_baseline(q.question, retriever, CONFIGS[config][1], settings, completion)

        rec.update(
            status=res.status, answer=res.answer,
            citations=[c.model_dump() for c in res.citations],
            latency_ms=res.latency_ms, tokens=res.prompt_tokens + res.completion_tokens,
            cost_usd=res.cost_usd, n_steps=len(res.steps), retrieved=res.retrieved,
            # best rerank score is only meaningful for B (hybrid_rerank scores)
            best_score=max((r["score"] for r in res.retrieved if "score" in r), default=None)
            if config == "B" else None,
        )
        rec["hit"] = page_hit(res.retrieved, q.expected_pages) if q.expected_pages else None

        if q.category == "unanswerable":
            rec["correct"] = res.status == "not_found"  # refusing IS the right answer
        elif res.status != "answered":
            rec["correct"] = False  # false refusal
        elif q.numeric:
            rec["correct"] = numeric_correct(res.answer, q.expected_answer, q.tolerance)
        else:
            rec["correct"], rec["judge_reason"] = judge(q, res.answer, settings, completion)
            rec["judge_used"] = True
    except Exception as e:  # noqa: BLE001 - one failed call must not kill a long eval run
        rec.update(error=f"{type(e).__name__}: {e}", correct=False, status="error",
                   answer="", hit=None, latency_ms=0, tokens=0, cost_usd=0.0, n_steps=0,
                   retrieved=[], best_score=None)
    return rec


TRANSIENT = ("Timeout", "ServiceUnavailableError", "RateLimitError", "APIConnectionError",
             "InternalServerError")
RETRIES = 3  # extra attempts after the first
RETRY_SLEEP = 20  # seconds; multiplied by the attempt number


def evaluate_one(
    q: Question,
    config: str,
    retriever: Retriever,
    settings: Settings,
    completion: Callable[..., Any],
) -> dict:
    """Run one question, retrying provider hiccups (503, timeout, 429) with a growing pause.
    Real wrong answers are never retried: only errors."""
    for attempt in range(RETRIES + 1):
        rec = _evaluate_once(q, config, retriever, settings, completion)
        transient = bool(rec["error"]) and rec["error"].startswith(TRANSIENT)
        if not transient or attempt == RETRIES:
            break
        time.sleep(RETRY_SLEEP * (attempt + 1))
    rec["attempts"] = attempt + 1
    return rec


def likely_cause(rec: dict) -> str:
    """Heuristic label for the failure table. A human should confirm each one."""
    if rec["error"]:
        return f"run error ({rec['error'][:80]})"
    if rec["category"] == "unanswerable":
        return "answered instead of refusing (hallucination or weak-evidence signal ignored)"
    if rec["status"] == "not_found":
        return ("false refusal: expected page was retrieved but model refused"
                if rec["hit"] else "false refusal after retrieval miss")
    if rec["hit"] is False:
        return "retrieval miss: no expected page in what the model saw"
    return "reasoning/extraction error: right page retrieved, wrong answer"


# ---------------------------------------------------------------- aggregation
def _mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def summarize(records: list[dict]) -> dict:
    out: dict[str, Any] = {}
    for cfg in CONFIGS:
        all_rs = [r for r in records if r["config"] == cfg]
        if not all_rs:
            continue
        # A run that errored out (API down) says nothing about answer quality: count it
        # separately instead of as a wrong answer.
        rs = [r for r in all_rs if not r["error"]]
        answerable = [r for r in rs if r["category"] != "unanswerable"]
        unans = [r for r in rs if r["category"] == "unanswerable"]
        with_pages = [r for r in rs if r["hit"] is not None]
        scores = {
            "answerable": [r["best_score"] for r in answerable if r["best_score"] is not None],
            "unanswerable": [r["best_score"] for r in unans if r["best_score"] is not None],
        }
        out[cfg] = {
            "name": CONFIGS[cfg][0],
            "n": len(rs),
            "n_total": len(all_rs),
            "hit_at_5": _mean([float(r["hit"]) for r in with_pages]),
            "answer_accuracy": _mean([float(r["correct"]) for r in answerable]),
            "refusal_accuracy": _mean([float(r["correct"]) for r in unans]),
            "false_refusal_rate": _mean([float(r["status"] == "not_found") for r in answerable]),
            "avg_latency_ms": _mean([r["latency_ms"] for r in rs]),
            "avg_tokens": _mean([r["tokens"] for r in rs]),
            "avg_cost_usd": _mean([r["cost_usd"] for r in rs]),
            "errors": len(all_rs) - len(rs),
            "accuracy_by_category": {
                cat: _mean([float(r["correct"]) for r in rs if r["category"] == cat])
                for cat in CATEGORIES
                if any(r["category"] == cat for r in rs)
            },
            "best_rerank_score": {
                k: ({"min": min(v), "mean": statistics.fmean(v), "max": max(v)} if v else None)
                for k, v in scores.items()
            } if cfg == "B" else None,
        }
    return out


def run_eval(
    questions: list[Question],
    retriever: Retriever,
    settings: Settings,
    completion: Callable[..., Any] | None = None,
    configs: tuple[str, ...] = ("A", "B", "C"),
) -> dict:
    if completion is None:
        import litellm

        completion = litellm.completion
    records = []
    for cfg in configs:
        for i, q in enumerate(questions, 1):
            rec = evaluate_one(q, cfg, retriever, settings, completion)
            records.append(rec)
            print(f"[{cfg}] {i}/{len(questions)} {q.id}: "
                  f"{'OK ' if rec['correct'] else 'BAD'} {rec['error'] or ''}")
    judged = [r for r in records if r["judge_used"]]
    sample = random.Random(0).sample(judged, min(MANUAL_SAMPLE, len(judged)))  # seeded
    return {
        "meta": {
            "date": datetime.now().isoformat(timespec="seconds"),
            "llm_model": settings.llm_model,
            "judge_model": settings.judge_model or settings.llm_model,
            "weak_score_threshold": settings.weak_score_threshold,
            "n_questions": len(questions),
        },
        "summary": summarize(records),
        "manual_recheck_sample": [
            {k: r[k] for k in ("id", "config", "question", "expected_answer", "answer",
                               "correct", "judge_reason")}
            for r in sample
        ],
        "records": records,
    }


# ---------------------------------------------------------------- output files
def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _num(x: float | None, div: float = 1, unit: str = "", digits: int = 1) -> str:
    return "n/a" if x is None else f"{x / div:.{digits}f}{unit}"


def render_results_md(res: dict) -> str:
    m, summ = res["meta"], res["summary"]
    lines = [
        "# Evaluation results", "",
        *(["> **DRY RUN: includes UNVERIFIED questions. Do not cite these numbers.**", ""]
          if m.get("dry_run") else []),
        f"Run on {m['date']} | model `{m['llm_model']}` | judge `{m['judge_model']}` | "
        f"{m['n_questions']} verified questions", "",
        "| Config | hit@5 | Answer acc. | Refusal acc. | False refusals | Avg latency | "
        "Avg tokens | Avg cost | Errors |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cfg, s in summ.items():
        cost = "n/a" if not s["avg_cost_usd"] else f"${s['avg_cost_usd']:.4f}"
        lines.append(
            f"| {cfg}) {s['name']} | {_pct(s['hit_at_5'])} | {_pct(s['answer_accuracy'])} | "
            f"{_pct(s['refusal_accuracy'])} | {_pct(s['false_refusal_rate'])} | "
            f"{_num(s['avg_latency_ms'], 1000, 's')} | {_num(s['avg_tokens'], 1, '', 0)} | "
            f"{cost} | {s['errors']} of {s['n_total']} |"
        )
    lines += ["", "Errors = runs that failed for infrastructure reasons (API busy, timeouts) even "
              "after retries; they are excluded from every other column.", "",
              "hit@5 for C = expected page appeared in any search/page-read result the "
              "agent saw, so it is not strictly comparable with A and B.", "",
              "## Accuracy by category", "",
              "| Config | " + " | ".join(CATEGORIES) + " |", "|---|" + "---|" * len(CATEGORIES)]
    for cfg, s in summ.items():
        cells = [_pct(s["accuracy_by_category"].get(c)) for c in CATEGORIES]
        lines.append(f"| {cfg} | " + " | ".join(cells) + " |")
    b = summ.get("B", {}).get("best_rerank_score")
    if b:
        lines += ["", "## Rerank scores of the top hit (config B), for threshold calibration", "",
                  "| Questions | min | mean | max |", "|---|---|---|---|"]
        for k, v in b.items():
            if v:
                lines.append(f"| {k} | {v['min']:.2f} | {v['mean']:.2f} | {v['max']:.2f} |")
        lines.append(f"\nCurrent WEAK_SCORE_THRESHOLD = {m['weak_score_threshold']}")
    return "\n".join(lines) + "\n"


def render_failures_md(res: dict) -> str:
    errs = [r for r in res["records"] if r["error"]]
    bad = [r for r in res["records"] if not r["correct"] and not r["error"]]
    lines = ["# Failure analysis", "",
             f"{len(bad)} wrong answers out of {len(res['records']) - len(errs)} scored runs "
             f"({len(errs)} further runs failed with API errors, listed at the end). "
             "'Likely cause' is an automatic heuristic: confirm by hand.", ""]
    for r in bad:
        lines += [
            f"## [{r['config']}] {r['id']} ({r['category']})",
            f"- **Question:** {r['question']}",
            f"- **Expected:** {r['expected_answer']}",
            f"- **Got ({r['status']}):** {r['answer'] or '-'}",
            f"- **Likely cause:** {likely_cause(r)}", "",
        ]
    if errs:
        lines += ["## Runs that failed with API errors (not wrong answers)", ""]
        lines += [f"- [{r['config']}] {r['id']}: {r['error'][:120]}" for r in errs]
    return "\n".join(lines) + "\n"


def write_outputs(res: dict, out_dir: str | Path) -> None:
    out = Path(out_dir)
    (out / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), "utf-8")
    (out / "results.md").write_text(render_results_md(res), "utf-8")
    (out / "failure_analysis.md").write_text(render_failures_md(res), "utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the FinRAG evaluation")
    ap.add_argument("--questions", default="eval/questions.json")
    ap.add_argument("--out-dir", default="eval")
    ap.add_argument("--configs", default="A,B,C")
    ap.add_argument("--rpm", type=float, default=12,
                    help="max LLM requests per minute (0 = no limit); default fits a 15 RPM tier")
    ap.add_argument("--dry-run", action="store_true",
                    help="smoke test: also score UNVERIFIED questions. Results are not citable, "
                    "so --out-dir must not be 'eval'")
    ap.add_argument("--ids", help="comma-separated question ids to run (default: all)")
    args = ap.parse_args()

    if args.dry_run and Path(args.out_dir).resolve() == Path("eval").resolve():
        raise SystemExit("--dry-run results include unverified questions: use another --out-dir.")
    all_qs = load_questions(args.questions)
    chosen = [q for q in all_qs if args.dry_run or q.verified]
    if args.ids:
        wanted = set(args.ids.split(","))
        chosen = [q for q in chosen if q.id in wanted]
    print(f"{len(chosen)} questions to run ({sum(q.verified for q in chosen)} verified, "
          f"{len(all_qs)} in file)")
    if not chosen:
        raise SystemExit("No verified questions: nothing to score, no results written.")

    import litellm

    settings = get_settings()
    settings.llm_fallback_model = ""  # one model per evaluation: no silent fallback mixing models
    res = run_eval(chosen, Retriever.from_disk(), settings,
                   completion=throttled(litellm.completion, args.rpm),
                   configs=tuple(args.configs.split(",")))
    if args.dry_run:
        res["meta"]["dry_run"] = True
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    write_outputs(res, args.out_dir)
    print(render_results_md(res))


if __name__ == "__main__":
    main()
