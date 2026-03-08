# Technical Design Document

**Autonomous Facebook & Instagram Ad Generation Engine**

This document summarizes the system design and architecture from the Pre-Search / Technical Design phase and aligns with the FAANG-style system design. Reference PDFs in this folder:

- **`docs/autonomous_ad_engine_presearch_design.pdf`** — Pre-search technical design (goals, architecture, iteration, experiments).
- **`docs/faang_style_autonomous_ad_engine_sysdesign.pdf`** — FAANG-style system design (services, decision engine, scalability, failure handling).

## 1. Problem overview

Modern AI can produce large volumes of ad copy, but most outputs are mediocre. The main challenge is **evaluation and iteration**: reliably telling good from bad and improving over time. This project builds an **Autonomous Ad Engine** that generates FB/IG ad copy, evaluates it on measurable dimensions, and iterates until quality meets a threshold. North star metric: **performance per token** (quality per API cost).

## 2. System goals

| Goal | Target |
|------|--------|
| Ads generated | ≥ 50 |
| Quality threshold | ≥ 7.0 average |
| Iteration cycles | ≥ 3 |
| Evaluation dimensions | 5 |
| Reproducibility | Seed-based |

## 3. High-level architecture

*FAANG-style flow: Input Brief → Generator Service → Evaluation Service → Decision Engine → Iteration Engine → Approved Ad Library.*

```
Ad Brief → Generator (LLM) → Evaluator (LLM Judge) → Decision: Score >= 7?
    Yes → Ad Library
    No  → Identify weakest dimension → Regenerate (targeted) → back to Evaluator
```

## 4. Core components

### 4.1 Ad generator

- **Input:** Structured brief (audience, product, goal, tone).
- **Output:** JSON with `primary_text`, `headline`, `description`, `cta`.
- **Model:** Gemini (recommended). Prompt includes brand voice, format constraints, and output schema.

### 4.2 Evaluator (most important)

- **Dimensions:** Clarity, Value Proposition, CTA, Brand Voice, Emotional Resonance.
- **Score range:** 1–10 per dimension; weighted aggregate → overall score.
- **Output:** Scores + rationales per dimension; used for iteration and reporting.
- **Weights:** Clarity 25%, Value Proposition 25%, Emotional Resonance 20%, CTA 15%, Brand Voice 15%.

### 4.3 Iteration engine (incl. Decision Engine)

- **Decision Engine:** Decides accept vs iterate from evaluator output; routes to Ad Library or Iteration Engine.
- **Loop:** Generate → Evaluate → if below 7.0, pick weakest dimension → targeted regeneration → re-evaluate.
- **Cap:** Max iterations per ad (e.g. 5); then mark as not accepted and keep best version.
- **Targeting:** Improvement prompt focuses on the weak dimension and its rationale (avoids full regeneration for efficiency).

### 4.4 Storage

- **Ad library:** Accepted ads + metadata (brief, scores, iteration_count, optional cost).
- **Evaluation logs:** Per-ad, per-dimension scores and rationales.
- **Implementation:** JSON files under `output/` for v1.

### 4.5 Metrics

- **Performance per token:** `avg_ad_quality / token_cost` per run/cycle.
- **Quality trend:** Average score per cycle for visualization.

## 5. Code layout

```
ad_engine/
  generate/     generator, prompt_templates, briefs
  evaluate/     evaluator, dimension_scorer, aggregator
  iterate/      optimizer, improvement_strategies
  storage/      ad_library
  metrics/      performance_metrics
  output/       export_reports, visualization
```

## 6. Outputs

- **ads_dataset.json** — Generated ads with full copy and scores.
- **evaluation_report.csv** — ad_id, overall_score, iteration_count, per-dimension scores.
- **iteration_quality_chart.png** — Quality trend over cycles (when matplotlib available).
- **Decision log** — docs/DECISION_LOG.md.

## 7. Failure handling

*(From both PDFs: evaluator drift, repetitive outputs, excessive iteration.)*

- **Infinite regeneration:** Max iterations per ad (default 6); then stop and record as not accepted.
- **Transient API failures:** Generator and evaluator use **retries with exponential backoff** (`ad_engine.utils.with_retry`) so rate limits or network blips don’t fail entire runs.
- **Mode collapse / repetitive outputs:** Documented for future diversity constraint; not auto-handled in v1.
- **Evaluator drift:** No auto-recalibration in v1; recommend periodic calibration with reference ads (e.g. via `scripts/calibrate_evaluator.py`).
- **Safeguards:** Iteration limits, (future) diversity constraints, (future) evaluator calibration against reference ads.

## 8. Scalability (FAANG-style)

- **Batch generation:** CLI runs N ads in sequence; structure supports `generate_ads(batch_size=...)` and parallel evaluation workers.
- **Modular services:** Generator, Evaluator, Iteration Engine, Ad Library, Metrics are separate modules; can be scaled or replaced independently.
- **Structured APIs:** Briefs and ads use JSON; evaluation results are structured for logging and reporting.
- **Context management:** Deliberate choice — each LLM call sees only system prompt + single user message (no cross-ad context); see Decision log §11.

## 9. Experiments framework

*(From pre-search PDFs: single vs multi-LLM, full vs targeted regeneration, cheap vs expensive models.)*

Planned comparisons:

| Experiment | Goal |
|------------|------|
| Single LLM vs multi-LLM evaluation | Measure evaluation reliability and consistency |
| Full regeneration vs targeted edits | Identify which improves quality faster per token |
| Cheap vs expensive model | Maximize performance per token |

See **`docs/EXPERIMENTS.md`** for how to run and record experiments.

## 10. Future work (v2 / v3)

- **v2:** Multimodal ads (image generation, visual evaluation), A/B variants, multi-model orchestration.
- **v3:** Self-healing loops, quality ratchet, performance-per-token tracking with real costs, agentic orchestration (Research → Writer → Editor → Evaluator → Optimizer), competitive intelligence (e.g. Meta Ad Library).

---

*This design aligns with the Pre-Search Technical Design Document and the FAANG-Style System Design PDFs in `docs/`.*
