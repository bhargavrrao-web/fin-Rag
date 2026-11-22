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

from app.config import Settings, get_settings
from app.tools import ToolBox, tool_schemas

MAX_STEPS = 6
PREVIEW_CHARS = 300

SYSTEM_PROMPT = """You are a research assistant answering questions about annual reports of \
Indian IT companies. Use ONLY the provided tools; never use outside knowledge.

Rules:
- Be concise.
- Use search_documents to find evidence. Use get_pages to read a page in full when a search \
hit looks right but you need the surrounding numbers or table.
- Use the calculator for ANY arithmetic (growth rates, margins, differences). Never compute \
in your head.
- ALWAYS cite: every fact in your answer must come from a page you saw in tool results.
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
    return FinalAnswer.model_validate_json(cleaned)


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
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    start = time.perf_counter()
    retried = False

    def call_llm(tool_choice: str) -> Any:
        resp = completion(
            model=settings.llm_model,
            messages=messages,
            tools=tool_schemas(),
            tool_choice=tool_choice,
            temperature=0,  # deterministic answers make the evaluation reproducible
            api_key=settings.llm_api_key or None,
        )
        usage = getattr(resp, "usage", None)
        if usage:
            result.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            result.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        result.cost_usd += _cost(resp)
        return resp.choices[0].message

    with _span("agent.run", settings, question=question):
        for step in range(max_steps):
            # On the last step forbid tools, so the model must produce an answer.
            msg = call_llm("none" if step == max_steps - 1 else "auto")
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
