# Rate Limits and Cost Considerations

Per project requirements: *"Document rate limits and cost considerations."*

## Gemini API

- **Rate limits:** Governed by [Google AI Studio / Gemini API quotas](https://ai.google.dev/pricing). Free tier has per-minute request and token limits; paid tier has higher limits. For 50+ ads with iteration (multiple calls per ad), expect to stay within free tier for small runs or need paid tier for batch runs.
- **Cost:** Pricing is per token (input + output). See [Gemini pricing](https://ai.google.dev/pricing). `gemini-1.5-flash` is lower cost than `gemini-1.5-pro`. This project does not record token usage automatically; add usage/cost tracking if you need performance-per-token metrics.
- **Mitigation:** Use a single LLM for both generation and evaluation in v1 to reduce calls; use `max_iterations` to cap regeneration; run with `--num-ads` as needed to stay within budget.

## Local runs

- **No PII:** Generated content does not include real user data; API calls send only briefs and ad copy.
- **Reproducibility:** Use `--seed` for deterministic brief order and model behavior where supported.
- **Cost awareness:** Each `run` makes at least `num_ads` generation calls and at least `num_ads` evaluation calls, plus additional calls for each iteration when score < 7.0. Total calls ≈ `num_ads * (1 + avg_evaluations + avg_regenerations)`.

## Documented elsewhere

- **Performance-per-token:** Structure is in place in `ad_engine.metrics.performance_metrics`; token cost is not populated automatically (see DECISION_LOG §7).
- **Limitations:** DECISION_LOG §9 documents that token cost is not measured in v1.
