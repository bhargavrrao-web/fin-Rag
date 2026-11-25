"""Hand-written tool-calling agent loop (no framework).

Loop: send messages + tool schemas -> if the model asks for tools, run them and append the
results -> repeat. When it replies without tool calls, that reply is the final JSON answer.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings, llm_kwargs
from app.tools import ToolBox, tool_schemas

MAX_STEPS = 6
PREVIEW_CHARS = 300

# Shared with baseline.py so every config answers in the same format.
JSON_FORMAT = """When you are done, reply with ONLY this JSON (no other text):
{"answer": "<text>", "citations": [{"company": "<lowercase>", "fiscal_year": <4-digit int>, \
"page": <int>}], "status": "answered" | "not_found"}
For not_found, use an empty citations list."""

SYSTEM_PROMPT = """You are a research assistant answering questions about annual reports of \
Indian IT companies. Use ONLY the provided tools; never use outside knowledge.

Rules:
- Be concise.
- Use search_documents to find evidence. Use get_pages to read a page in full when a search \
hit looks right but you need the surrounding numbers or table.
- Use the calculator for ANY arithmetic (growth rates, margins, differences). Never compute \
in your head.
- ALWAYS cite: every fact in your answer must come from a page you saw in tool results.
- Figures such as attrition or headcount often sit in running prose, not tables. If the top \
hits do not contain the figure, search again with top_k 10 before giving up.
- The "answer" field must never be empty, even for not_found.
- If search results say evidence_weak, try at most one differently-worded search. If the \
documents still do not contain the answer, answer with status "not_found". Do not guess.

When you are done, reply with ONLY this JSON (no other text):
{"answer": "<text>", "citations": [{"company": "<lowercase>", "fiscal_year": <4-digit int>, \
"page": <int>}], "status": "answered" | "not_found"}
For not_found, use an empty citations list."""


class Citation(BaseModel):
    company: str
    fiscal_year: int
    page: int
    passage: str = ""


class FinalAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    status: Literal["answered", "not_found"]


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation]
    status: str
    steps: list[dict] = field(default_factory=list)  # trace: {tool, args, result_preview, ms}
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    retrieved: list[dict] = field(default_factory=list)  # pages the tools showed the model


_logfire_ready = False


def _span(name: str, settings: Settings, **attrs: Any) -> AbstractContextManager:
    """Logfire span if LOGFIRE_TOKEN is set, otherwise a do-nothing context manager."""
    global _logfire_ready
    if not settings.logfire_token:
        return nullcontext()
    import logfire

    if not _logfire_ready:
        logfire.configure(token=settings.logfire_token)
        _logfire_ready = True
    return logfire.span(name, **attrs)


def parse_final(text: str | None) -> FinalAnswer:
    """Parse the model's final message. Tolerates ```json fences, which models love to add."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    final = FinalAnswer.model_validate_json(cleaned)
    if not final.answer.strip():
        # An empty answer would show the user a blank result; make the model say something.
        raise ValueError(
            "the answer field is empty. Write one plain sentence: the answer, or for "
            "not_found, what you searched for and did not find."
        )
    return final


def add_usage(result: AgentResult, response: Any) -> None:
    """Accumulate token counts and (if the model is priced) cost from one LLM response."""
    usage = getattr(response, "usage", None)
    if usage:
        result.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        result.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
    result.cost_usd += _cost(response)


def _cost(response: Any) -> float:
    try:
        import litellm

        return float(litellm.completion_cost(completion_response=response))
    except Exception:  # noqa: BLE001 - unknown/custom models have no price; cost is optional
        return 0.0


def run_agent(
    question: str,
    toolbox: ToolBox,
    settings: Settings | None = None,
    completion: Callable[..., Any] | None = None,
    max_steps: int = MAX_STEPS,
) -> AgentResult:
    """`completion` defaults to litellm.completion; tests pass a scripted fake."""
    settings = settings or get_settings()
    if completion is None:
        import litellm

        completion = litellm.completion

    result = AgentResult(answer="", citations=[], status="not_found")
    docs = toolbox.describe_documents()
    system = SYSTEM_PROMPT
    if docs:  # the model cannot guess our file-name slugs (e.g. 'techm'), so tell it
        system += f"\n\nIndexed documents (use these exact company names in tool calls): {docs}"
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    toolbox.seen.clear()
    start = time.perf_counter()
    retried = False

    def call_llm(tool_choice: str) -> Any:
        resp = completion(
            model=settings.llm_model,
            messages=messages,
            tools=tool_schemas(),
            tool_choice=tool_choice,
            temperature=0,  # deterministic answers make the evaluation reproducible
            **llm_kwargs(settings),
        )
        add_usage(result, resp)
        return resp.choices[0].message

    with _span("agent.run", settings, question=question):
        for step in range(max_steps):
            last = step == max_steps - 1
            if last:
                # Some providers ignore tool_choice="none", so also tell the model in words.
                messages.append(
                    {
                        "role": "user",
                        "content": "No more tool calls are allowed. Using only what you have "
                        "found so far, reply now with the final JSON answer "
                        "(status not_found if the evidence is insufficient).",
                    }
                )
            msg = call_llm("none" if last else "auto")
            tool_calls = getattr(msg, "tool_calls", None) or []

            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )
                for tc in tool_calls:
                    name, raw = tc.function.name, tc.function.arguments
                    t0 = time.perf_counter()
                    with _span(f"tool.{name}", settings, args=raw):
                        output = toolbox.call(name, raw)  # errors come back as text
                    result.steps.append(
                        {
                            "tool": name,
                            "args": raw,
                            "result_preview": output[:PREVIEW_CHARS],
                            "ms": int((time.perf_counter() - t0) * 1000),
                        }
                    )
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})
                continue

            # No tool calls: this should be the final JSON answer.
            try:
                final = parse_final(msg.content)
            except (ValidationError, ValueError) as e:
                if retried:
                    result.answer = "The model did not return a valid answer."
                    break
                retried = True  # one retry, telling the model exactly what was wrong
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Your reply was not valid. Error: {str(e)[:300]}\n"
                        "Reply again with ONLY the JSON object described in the instructions.",
                    }
                )
                continue
            result.answer, result.citations, result.status = (
                final.answer,
                final.citations,
                final.status,
            )
            break
        else:
            result.answer = "The agent ran out of steps before reaching an answer."

    result.latency_ms = int((time.perf_counter() - start) * 1000)
    result.retrieved = [
        {"company": c, "fiscal_year": y, "page": p} for c, y, p in toolbox.seen
    ]
    return result


def result_to_dict(r: AgentResult) -> dict:
    """JSON-friendly form for the API (Phase 5)."""
    return {
        "answer": r.answer,
        "citations": [c.model_dump() for c in r.citations],
        "status": r.status,
        "steps": r.steps,
        "latency_ms": r.latency_ms,
        "tokens": {"prompt": r.prompt_tokens, "completion": r.completion_tokens},
        "cost_usd": r.cost_usd,
    }


if __name__ == "__main__":
    import sys

    from app.retrieval import Retriever

    s = get_settings()
    box = ToolBox(Retriever.from_disk(), weak_threshold=s.weak_score_threshold)
    print(json.dumps(result_to_dict(run_agent(" ".join(sys.argv[1:]), box, s)), indent=2))
