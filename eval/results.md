# Evaluation results

Run on 2026-11-25T11:35:25 | model `gemini/gemini-3.5-flash-lite` | judge `gemini/gemini-3.5-flash-lite` | 40 verified questions

| Config | hit@5 | Answer acc. | Refusal acc. | False refusals | Avg latency | Avg tokens | Avg cost | Errors |
|---|---|---|---|---|---|---|---|---|
| A) vector-only + 1 LLM call | 24% | 52% | 100% | 45% | 7.4s | 4508 | $0.0015 | 0 of 40 |
| B) hybrid+rerank + 1 LLM call | 55% | 61% | 100% | 24% | 6.2s | 3872 | $0.0013 | 0 of 40 |
| C) full agent | 67% | 85% | 100% | 3% | 23.1s | 17448 | $0.0047 | 0 of 40 |

Errors = runs that failed for infrastructure reasons (API busy, timeouts) even after retries; they are excluded from every other column.

hit@5 for C = expected page appeared in any search/page-read result the agent saw, so it is not strictly comparable with A and B.

## Accuracy by category

| Config | lookup | multi_step | comparison | unanswerable |
|---|---|---|---|---|
| A | 67% | 70% | 0% | 100% |
| B | 80% | 60% | 25% | 100% |
| C | 93% | 100% | 50% | 100% |

## Rerank scores of the top hit (config B), for threshold calibration

| Questions | min | mean | max |
|---|---|---|---|
| answerable | -0.57 | 4.42 | 8.15 |
| unanswerable | -5.32 | 0.98 | 5.40 |

Current WEAK_SCORE_THRESHOLD = 0.0
