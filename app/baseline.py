"""Single-shot RAG baseline: retrieve once, then ONE LLM call. No tools, no loop.

Used by the evaluation as configs A (vector) and B (hybrid_rerank) so we can measure what
the agent adds on top of plain retrieve-then-read.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.agent import JSON_FORMAT, AgentResult, add_usage, parse_final
from app.config import Settings, get_settings
from app.retrieval import Retriever

BASELINE_PROMPT = """You answer questions about annual reports of Indian IT companies using \
ONLY the context passages provided. Never use outside knowledge. Be concise and cite the \
pages you used. If the context does not contain the answer, use status "not_found".

""" + JSON_FORMAT


def run_baseline(
    question: str,
    retriever: Retriever,
    mode: str,
    settings: Settings | None = None,
    completion: Callable[..., Any] | None = None,
    top_k: int = 5,
) -> AgentResult:
    settings = settings or get_settings()
    if completion is None:
        import litellm

        completion = litellm.completion

    start = time.perf_counter()
    hits = retriever.search(question, top_k=top_k, mode=mode)  # no company filter: the
    # baseline has no way to know which company the question is about
    context = "\n\n".join(
        f"[{h.company} FY{h.fiscal_year % 100}, page {h.page}]\n{h.text}" for h in hits
    )
    messages = [
        {"role": "system", "content": BASELINE_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    result = AgentResult(answer="", citations=[], status="not_found")
    result.retrieved = [
        {"company": h.company, "fiscal_year": h.fiscal_year, "page": h.page, "score": h.score}
        for h in hits
    ]

    # Same single retry on malformed JSON as the agent, so format errors don't skew the
    # comparison. This is the only case where the baseline makes a second call.
    for attempt in range(2):
        resp = completion(
            model=settings.llm_model,
            messages=messages,
            temperature=0,
            api_key=settings.llm_api_key or None,
        )
        add_usage(result, resp)
        content = resp.choices[0].message.content
        try:
            final = parse_final(content)
        except (ValidationError, ValueError) as e:
            if attempt == 1:
                result.answer = "The model did not return a valid answer."
                break
            messages.append({"role": "assistant", "content": content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": f"Your reply was not valid. Error: {str(e)[:300]}\n"
                    "Reply again with ONLY the JSON object.",
                }
            )
            continue
        result.answer, result.citations, result.status = (
            final.answer,
            final.citations,
            final.status,
        )
        break

    result.latency_ms = int((time.perf_counter() - start) * 1000)
    return result
