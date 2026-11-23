"""Eval harness tests: scoring helpers and an end-to-end run with a fake LLM (offline)."""
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.retrieval import Hit
from eval.run_eval import (
    ExpectedPage,
    Question,
    extract_numbers,
    likely_cause,
    load_questions,
    numeric_correct,
    page_hit,
    render_failures_md,
    render_results_md,
    run_eval,
)

SETTINGS = Settings(_env_file=None, llm_model="fake")


def q(id="q1", category="lookup", expected="Revenue was 1,000 crore", numeric=False, pages=None,
      verified=True):
    pages = [{"company": "acme", "fiscal_year": 24, "page": 7}] if pages is None else pages
    return Question(id=id, category=category, question="What was revenue?",
                    expected_answer=expected, expected_pages=pages, numeric=numeric,
                    verified=verified)


# ---------------------------------------------------------------- helpers
def test_extract_numbers():
    assert extract_numbers("Rs 1,53,670 crore, up 4.7%") == [153670.0, 4.7]
    assert extract_numbers("no digits") == []


def test_numeric_correct_relative_tolerance():
    assert numeric_correct("It was 1,005 crore", "1000", 0.01)
    assert not numeric_correct("It was 1,050 crore", "1000", 0.01)
    assert numeric_correct("grew 20.0% to 1200", "20", 0.01)  # any number may match
    assert not numeric_correct("no number", "1000", 0.01)


def test_page_hit_normalises_year():
    exp = [ExpectedPage(company="Acme", fiscal_year=24, page=7)]
    assert page_hit([{"company": "acme", "fiscal_year": 2024, "page": 7}], exp)
    assert not page_hit([{"company": "acme", "fiscal_year": 2024, "page": 8}], exp)


def test_question_validation():
    with pytest.raises(ValueError):
        q(pages=[])  # answerable but no expected page
    with pytest.raises(ValueError):
        q(numeric=True, expected="lots")  # numeric without a number
    assert q(category="unanswerable", pages=[]).expected_pages == []


def test_load_questions_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "q.json"
    one = q().model_dump()
    p.write_text(json.dumps([one, one]))
    with pytest.raises(ValueError):
        load_questions(p)


# ---------------------------------------------------------------- end to end
class StubRetriever:
    chunks: list = []

    def search(self, query, company=None, fiscal_year=None, top_k=5, mode="hybrid_rerank"):
        return [Hit(0, "Revenue was 1,000 crore", "acme", 2024, 7, 3.0, "vector")]


def fake_completion(**kw):
    """One function plays the baseline LLM, the agent LLM and the judge."""
    system = kw["messages"][0]["content"]
    user = kw["messages"][-1]["content"]
    if "STRICT grader" in system:
        ok = "1,000" in user.split("MODEL:")[1]
        content = json.dumps({"correct": ok, "reason": "stub"})
    elif "unanswerable" in user:  # question text marks the unanswerable case
        content = json.dumps({"answer": "n/a", "citations": [], "status": "not_found"})
    else:
        content = json.dumps({"answer": "Revenue was 1,000 crore", "status": "answered",
                              "citations": [{"company": "acme", "fiscal_year": 2024, "page": 7}]})
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def test_run_eval_end_to_end():
    unans = Question(id="u1", category="unanswerable", question="unanswerable thing?",
                     expected_answer="not in documents")
    questions = [q("a", numeric=True, expected="1000"), q("b"), unans]
    res = run_eval(questions, StubRetriever(), SETTINGS, completion=fake_completion)

    for cfg in "ABC":
        s = res["summary"][cfg]
        assert s["n"] == 3
        assert s["answer_accuracy"] == 1.0 and s["refusal_accuracy"] == 1.0
    # unanswerable questions have no expected pages, so they are excluded from hit@5
    assert res["summary"]["A"]["hit_at_5"] == res["summary"]["B"]["hit_at_5"] == 1.0
    assert res["summary"]["C"]["hit_at_5"] == 0.0  # the fake agent never searched
    assert res["summary"]["B"]["best_rerank_score"]["answerable"]["max"] == 3.0
    assert res["summary"]["C"]["avg_tokens"] == 15  # agent answered in one call
    md = render_results_md(res)
    assert "| A) vector-only" in md
    assert "0 wrong answers" in render_failures_md(res)
    # judged answers (only question "b") end up in the manual re-check sample
    assert {r["id"] for r in res["manual_recheck_sample"]} == {"b"}


def test_wrong_answers_land_in_failure_analysis():
    def refusing(**kw):
        content = json.dumps({"answer": "dunno", "citations": [], "status": "not_found"})
        msg = SimpleNamespace(content=content, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

    res = run_eval([q("a")], StubRetriever(), SETTINGS, completion=refusing, configs=("B",))
    assert res["summary"]["B"]["false_refusal_rate"] == 1.0
    assert "false refusal" in likely_cause(res["records"][0])
    assert "[B] a" in render_failures_md(res)


def test_llm_errors_are_recorded_not_raised():
    def boom(**kw):
        raise RuntimeError("api down")

    res = run_eval([q("a")], StubRetriever(), SETTINGS, completion=boom, configs=("A",))
    rec = res["records"][0]
    assert rec["correct"] is False and "api down" in rec["error"]
    assert res["summary"]["A"]["errors"] == 1


def test_throttle_spaces_calls_apart():
    from eval.run_eval import throttled

    now, slept = [0.0], []

    def fake_sleep(sec):
        slept.append(sec)
        now[0] += sec

    wrapped = throttled(lambda **kw: "ok", rpm=12, clock=lambda: now[0], sleep=fake_sleep)
    assert [wrapped() for _ in range(3)] == ["ok"] * 3
    assert slept == [5.0, 5.0]  # first call is immediate; then 60/12 = 5 s between calls
    assert throttled(print, rpm=0) is print  # rpm 0 disables throttling


def test_verify_helper_marks_only_requested_ids(tmp_path):
    from eval.verify import mark_verified, render_checklist

    f = tmp_path / "q.json"
    base = {"question": "?", "expected_answer": "a", "expected_pages": [], "numeric": False,
            "tolerance": 0.01, "verified": False, "category": "unanswerable"}
    f.write_text(json.dumps([{**base, "id": "a"}, {**base, "id": "b"}]))
    mark_verified(["a"], f)
    data = json.loads(f.read_text())
    assert [q["verified"] for q in data] == [True, False]
    assert "- [x] **a**" in render_checklist(f) and "- [ ] **b**" in render_checklist(f)
    with pytest.raises(SystemExit):
        mark_verified(["zzz"], f)


def test_dry_run_banner_and_refusal_to_write_into_eval(monkeypatch):
    import sys

    from eval import run_eval as ev

    res = run_eval([q("a")], StubRetriever(), SETTINGS, completion=fake_completion, configs=("A",))
    res["meta"]["dry_run"] = True
    assert "DRY RUN" in render_results_md(res)
    assert "DRY RUN" not in render_results_md(run_eval(
        [q("a")], StubRetriever(), SETTINGS, completion=fake_completion, configs=("A",)))
    monkeypatch.setattr(sys, "argv", ["run_eval", "--dry-run", "--out-dir", "eval"])
    with pytest.raises(SystemExit, match="another --out-dir"):
        ev.main()
