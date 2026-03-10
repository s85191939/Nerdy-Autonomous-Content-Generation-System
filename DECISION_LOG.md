# Decision Log

Documenting design choices, tradeoffs, and limitations for the Autonomous Ad Generation System.

**What we're really being evaluated on:** Problem decomposition, taste and judgment, creative agency, systems thinking, iteration methodology, and this log itself. The README summarizes how this project addresses those criteria; this log is the main place we show reasoning and tradeoffs.

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

## 7. Performance-per-token and ROI tracking

**Decision:** Implement token tracking and cost estimation so ROI is measurable: "was it worth the tokens?"

**Rationale:** The real metric is value per token (or per dollar), not just "did the AI generate something?" We added `TokenTracker` (input/output tokens from Gemini, OpenRouter, OpenAI responses), estimated cost per run, and ROI metrics: accepted ads per 1K tokens, score per dollar. Run history is persisted to `output/run_history.json` and surfaced on the **ROI Dashboard** (`/dashboard`).

**Tradeoff:** Cost is estimated from list pricing; actual billing may differ. Token counts are accurate when the API returns usage (Gemini, OpenRouter, OpenAI all do).

---

## 8. Reproducibility

**Decision:** Support a `seed` argument for the generator and evaluator (passed to Gemini where supported) and for brief sampling (`get_briefs_for_count(count, seed)`).

**Rationale:** Assignment requires "Deterministic with seeds" and reproducible runs for comparison.

**Tradeoff:** Gemini's actual determinism depends on the API; we document that and use seed for brief order and any local RNG.

---

## 9. Limitations (honest)

- **LLM evaluator bias:** Scores may be inconsistent or biased toward certain phrasings.
- **No real campaign data:** Quality is predicted, not measured by clicks/conversions.
- **Brand voice:** Calibration depends on prompt quality and optional reference ads from Slack.
- **Token cost:** Now measured automatically (see §7). TokenTracker and run_history.json feed the ROI dashboard.
- **Single channel:** Only FB/IG copy; no email, landing pages, or creative images in v1.
- **Confidence scoring:** Implemented: each dimension has a 1–10 confidence score and the evaluator returns an aggregate; low confidence signals uncertainty.

---

## 10. What we did not do (and what we did) — v2 & v3

- **Multi-agent (research/writer/editor/evaluator):** **v3 implemented:** `ad_engine/agents/` provides ResearcherAgent, WriterAgent, EditorAgent, EvaluatorAgent and `run_for_brief_agentic()`; the main pipeline uses IterationEngine (same flow, same components). Agentic orchestration is available for explicit agent-based runs.
- **Competitive intelligence / Meta Ad Library:** **v3 implemented:** `ad_engine/competitor/insights.py` extracts patterns (hooks, CTAs, tone angles) from competitor ads; `scripts/run_competitive_intel.py` accepts a JSON of ads (exported/copied from Meta Ad Library) and writes `output/competitor_insights.json`. Pipeline loads these insights when generating.
- **Image generation:** Out of scope for v1; v2 has image generator (Imagen when available).
- **Visual evaluation (v2):** Implemented as text-based scoring (image concept + ad copy) for brand consistency and engagement potential when an image is generated; no vision API.
- **A/B variants (v2):** Implemented: `--num-variants` / `num_variants` with distinct creative angles (question/stat/story hook) and `variant_id` / `variant_angle` in export.
- **Self-healing loops (v3):** **Implemented:** After each run we compare avg score to the previous run; if quality drops by ≥0.5 we write `output/self_heal_suggestion.txt` with a suggested fix (recalibrate or iterate_campaign).
- **Quality ratchet (v3):** **Implemented:** `ad_engine/metrics/quality_ratchet.py` tracks best avg score so far; evaluation summary includes "Quality ratchet: best so far = X, floor = Y (standards only go UP)."
- **Performance-per-token (v3):** Already implemented: TokenTracker, run_history.json, ROI dashboard, performance_per_token in PerformanceMetrics.
- **Agentic orchestration (v3):** See first bullet — Researcher, Writer, Editor, Evaluator agents in `ad_engine/agents/`.

---

## 11. Context management (deliberate choice)

**Decision:** Each LLM call sees only what it needs. Generator: system prompt (brand + format) + single user message (brief or improvement instruction). Evaluator: system prompt (rubrics + confidence) + single user message (ad JSON). No cross-ad context; no long conversation history.

**Rationale:** Keeps costs predictable, avoids context drift, and makes it easy to reason about what each call "knows." Batch runs are independent per ad.

**Tradeoff:** We don't pass "what worked on similar ads" into the generator; that could be a future enhancement.

---

## 12. Human-in-the-loop (when to intervene)

**Decision:** We do not build an explicit "human approval" gate into the pipeline. Human intervention is expected at these points:

- **Before scaling:** Run `scripts/calibrate_evaluator.py` on reference ads (good/bad) from Slack. If good ads score below 7.0 or bad ads score above, adjust prompts or add reference ads before trusting scores.
- **After a run:** Review `evaluation_summary.txt` and, if needed, inspect rejected ads in `ads_dataset.json` to spot systematic evaluator drift or bad copy.
- **When calibration fails:** Add or replace reference ads in `examples/reference_ads_sample.json` and re-run calibration; do not proceed to 50+ ads until the evaluator separates good from bad.

**Rationale:** The spec leaves "When should a human intervene?" as a design choice. We keep the pipeline autonomous for batch runs but document when a human should step in to protect quality (calibration and spot checks).

---

## 13. Failed approaches and where it breaks

**Honest reflection:** What we tried or considered that didn't work or would break.

- **Full ad regeneration every iteration:** We tried a variant that always regenerated from the brief instead of targeted improvement. It used more tokens and often lost good parts of the ad; we switched to targeted regeneration and kept it.
- **No retries:** Early version had no retries on API errors. Transient rate limits or network blips failed entire runs. We added `with_retry` (exponential backoff) around generator and evaluator calls so the system recovers from transient failures.
- **Confidence ignored in threshold:** We could gate "publishable" on both score ≥ 7.0 and confidence ≥ 6. We didn't: threshold is score-only so we don't over-reject when the model is conservatively uncertain. Confidence is still in the report for human review.
- **Where it breaks:** If the evaluator consistently scores bad ads high (e.g. generic "we have tutors" copy), the library will accept them. Calibration against reference ads (see `scripts/calibrate_evaluator.py`) is required before trusting scores. If Gemini returns malformed JSON, we raise; we don't fall back to a default score.

---

*This log was written to reflect the reasoning behind the implementation, not only the implementation itself.*
