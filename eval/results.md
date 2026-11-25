# Evaluation results

Run on 2026-11-23T23:07:58 | model `gemini/gemini-3.5-flash-lite` | judge `gemini/gemini-3.5-flash-lite` | 5 verified questions

| Config | hit@5 | Answer acc. | Refusal acc. | False refusals | Avg latency | Avg tokens | Avg cost | Errors |
|---|---|---|---|---|---|---|---|---|
| A) vector-only + 1 LLM call | 0% | 75% | 100% | 25% | 14.6s | 3688 | $0.0012 | 0 of 5 |
| B) hybrid+rerank + 1 LLM call | 50% | 100% | 100% | 0% | 8.2s | 3630 | $0.0013 | 0 of 5 |
| C) full agent | 75% | 75% | 100% | 0% | 24.7s | 12798 | $0.0039 | 0 of 5 |

Errors = runs that failed for infrastructure reasons (API busy, timeouts) even after retries; they are excluded from every other column.

hit@5 for C = expected page appeared in any search/page-read result the agent saw, so it is not strictly comparable with A and B.

## Accuracy by category

| Config | lookup | multi_step | comparison | unanswerable |
|---|---|---|---|---|
| A | 100% | 100% | 0% | 100% |
| B | 100% | 100% | 100% | 100% |
| C | 100% | 100% | 0% | 100% |

## Rerank scores of the top hit (config B), for threshold calibration

| Questions | min | mean | max |
|---|---|---|---|
| answerable | 1.34 | 5.56 | 7.81 |
| unanswerable | -5.32 | -5.32 | -5.32 |

Current WEAK_SCORE_THRESHOLD = 0.0
