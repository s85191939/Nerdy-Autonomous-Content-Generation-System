# Experiments Framework

The pre-search and FAANG-style design PDFs call out three experiment areas. This doc describes how to run and compare them.

## Experiment 1: Single vs multi-LLM evaluation

**Goal:** Measure whether a separate model for evaluation improves reliability vs using the same model for generation and evaluation.

**How to run:**

- **Single LLM (baseline):** Use one Gemini model for both `AdGenerator` and `Evaluator` (current default).
- **Multi-LLM:** Use Gemini for generation and a different model (e.g. another Gemini config or a different API) for `Evaluator`. Implement by passing a different `model` into `Evaluator(seed=...)` when constructing the pipeline.

**Metrics:** Variance of scores on the same ad across runs; correlation with human preference if you have a small labeled set.

---

## Experiment 2: Full regeneration vs targeted edits

**Goal:** Identify which improves quality faster per token — regenerating the whole ad vs improving only the weak dimension.

**How to run:**

- **Targeted (current):** `IterationEngine` calls `generator.improve(ad, weak_dimension, rationale)` so the model rewrites with a focused prompt.
- **Full regeneration:** In `IterationEngine.run_for_brief`, when score < 7.0, call `generator.generate(brief)` again (optionally add “previous ad was scored X; try again” to the brief). Compare iteration count and total tokens to reach threshold.

**Metrics:** Number of iterations to reach ≥7.0; total tokens used per accepted ad.

---

## Experiment 3: Cheap vs expensive model

**Goal:** Maximize performance per token (quality / cost).

**How to run:**

- Use a smaller/cheaper model (e.g. `gemini-1.5-flash`) vs a larger one (e.g. `gemini-1.5-pro`) for generation and/or evaluation.
- Track cost per ad (if your API provides token/cost) and record in `PerformanceMetrics.record_run(..., token_cost=...)`.
- Compare `performance_per_token` and acceptance rate across runs.

**Metrics:** `performance_per_token`; % of ads accepted at ≥7.0.

---

## Recording results

- Log config (model names, single vs multi-LLM, targeted vs full) in `docs/DECISION_LOG.md` or a separate `docs/experiments_log.md`.
- Save outputs per run: `python -m ad_engine.cli run --num-ads 20 --seed 42` and copy `output/ads_dataset.json` and `output/evaluation_report.csv` to something like `output/exp1_single_llm/`, `output/exp2_targeted/`, etc., for comparison.
