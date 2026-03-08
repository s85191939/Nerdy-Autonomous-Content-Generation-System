# Decision Log

Documenting design choices, tradeoffs, and limitations for the Autonomous Ad Generation System.

## 1. Evaluation-first architecture

**Decision:** Build the evaluator before scaling the generator, and calibrate on reference ads.

**Rationale:** The assignment states that "the system that surfaces only its best work wins" and "the hardest part isn't generation—it's evaluation." We treat evaluation as the critical path: if the LLM judge cannot reliably separate good from bad ads, iteration cannot improve quality.

**Tradeoff:** More upfront prompt and schema work for evaluation; generation stays a single LLM call per ad.

---

## 2. Single LLM for both generation and evaluation

**Decision:** Use one model (Gemini) for ad generation and for LLM-as-judge evaluation in v1.

**Rationale:** Simplifies setup, reduces cost and latency for the initial pipeline. The design doc allows "Single LLM for both generation and evaluation is fine."

**Tradeoff:** Possible bias (same model may favor its own style). Mitigation: clear rubrics, structured JSON output, and optional future calibration with reference ads.

---

## 3. Dimension weights

**Decision:** Use fixed weights: Clarity 25%, Value Proposition 25%, Emotional Resonance 20%, CTA 15%, Brand Voice 15%.

**Rationale:** Aligns with the Pre-Search TDD and prioritizes message clarity and value; CTA and brand voice are necessary but secondary for "stops the scroll" primary text.

**Tradeoff:** Weights are not tuned to real campaign performance. Documented as a limitation; could be made configurable later.

---

## 4. Iteration: full regeneration vs targeted edit

**Decision:** Use targeted regeneration: identify weakest dimension, then call the generator with an improvement prompt for that dimension only.

**Rationale:** Targeted prompts are cheaper and more interpretable than regenerating the whole ad each time. We can still regenerate the full ad in one call by passing the previous ad + weak dimension + rationale.

**Tradeoff:** May under-explore; some ads might need a full rewrite. Max-iterations cap (default 6) prevents infinite loops and supports 5+ cycles per ad.

---

## 5. Failure handling

**Decision:**  
- Max iterations per ad = 6 (so we can demonstrate 5+ iteration cycles); after that, mark as not accepted and keep the best version.  
- No automatic diversity penalty in v1 (documented as future work).  
- Evaluator drift: no automatic recalibration in v1; recommend periodic calibration with reference ads.

**Rationale:** Keeps v1 simple and deterministic. Decision log and evaluation report make it clear which ads failed and after how many iterations.

---

## 6. Storage: JSON files vs database

**Decision:** Persist ad library and evaluation logs as JSON files under `output/`.

**Rationale:** One-command setup without DB; easy to version and inspect; sufficient for 50+ ads and reports.

**Tradeoff:** Not suitable for very large scale or concurrent writers; can be replaced with SQLite or a DB later without changing the public API of `AdLibrary`.

---

## 7. Performance-per-token tracking

**Decision:** Implement a `PerformanceMetrics` module that can record (cycle, avg_score, token_cost, num_ads) and compute performance_per_token = avg_score / token_cost. No automatic token counting in v1.

**Rationale:** API clients used here do not always expose token usage easily; manual or optional instrumentation keeps the pipeline runnable without extra APIs. Structure is in place for v2/v3 to plug in real costs.

**Tradeoff:** Metric is 0 or placeholder until token/cost tracking is added.

---

## 8. Reproducibility

**Decision:** Support a `seed` argument for the generator and evaluator (passed to Gemini where supported) and for brief sampling (`get_briefs_for_count(count, seed)`).

**Rationale:** Assignment requires "Deterministic with seeds" and reproducible runs for comparison.

**Tradeoff:** Gemini’s actual determinism depends on the API; we document that and use seed for brief order and any local RNG.

---

## 9. Limitations (honest)

- **LLM evaluator bias:** Scores may be inconsistent or biased toward certain phrasings.
- **No real campaign data:** Quality is predicted, not measured by clicks/conversions.
- **Brand voice:** Calibration depends on prompt quality and optional reference ads from Slack.
- **Token cost:** Not measured automatically in v1; performance_per_token is structural only until wired to usage APIs.
- **Single channel:** Only FB/IG copy; no email, landing pages, or creative images in v1.
- **Confidence scoring:** Implemented: each dimension has a 1–10 confidence score and the evaluator returns an aggregate; low confidence signals uncertainty.

---

## 10. What we did not do (and why)

- **Multi-agent (research/writer/editor/evaluator):** Deferred to v3; single generator + single evaluator is sufficient for 50+ ads and 3+ cycles.
- **Competitive intelligence / Meta Ad Library:** Deferred to v3; manual study recommended in README.
- **Image generation:** Out of scope for v1; structure allows a separate creative module later.
- **Self-healing loops:** Deferred to v3; current loop is fixed max iterations and threshold.

---

## 11. Context management (deliberate choice)

**Decision:** Each LLM call sees only what it needs. Generator: system prompt (brand + format) + single user message (brief or improvement instruction). Evaluator: system prompt (rubrics + confidence) + single user message (ad JSON). No cross-ad context; no long conversation history.

**Rationale:** Keeps costs predictable, avoids context drift, and makes it easy to reason about what each call “knows.” Batch runs are independent per ad.

**Tradeoff:** We don’t pass “what worked on similar ads” into the generator; that could be a future enhancement.

---

## 12. Failed approaches and where it breaks

**Honest reflection:** What we tried or considered that didn’t work or would break.

- **Full ad regeneration every iteration:** We tried a variant that always regenerated from the brief instead of targeted improvement. It used more tokens and often lost good parts of the ad; we switched to targeted regeneration and kept it.
- **No retries:** Early version had no retries on API errors. Transient rate limits or network blips failed entire runs. We added `with_retry` (exponential backoff) around generator and evaluator calls so the system recovers from transient failures.
- **Confidence ignored in threshold:** We could gate “publishable” on both score ≥ 7.0 and confidence ≥ 6. We didn’t: threshold is score-only so we don’t over-reject when the model is conservatively uncertain. Confidence is still in the report for human review.
- **Where it breaks:** If the evaluator consistently scores bad ads high (e.g. generic “we have tutors” copy), the library will accept them. Calibration against reference ads (see `scripts/calibrate_evaluator.py`) is required before trusting scores. If Gemini returns malformed JSON, we raise; we don’t fall back to a default score.

---

*This log was written to reflect the reasoning behind the implementation, not only the implementation itself.*
