# Quality Improvement Metrics and Visualizations

Submission requirement: quality improvement metrics and visualizations.

## What We Track

| Metric | Where it lives | Meaning |
|--------|----------------|--------|
| **Per-ad scores** | `evaluation_report.csv`, `ads_dataset.json` | Each ad has overall_score (1–10) and per-dimension scores (clarity, value_proposition, cta, brand_voice, emotional_resonance). |
| **Iteration history** | `ads_dataset.json` → `iteration_history` | For each ad, we store per-cycle: iteration number, overall_score, scores per dimension, and **targeted_dimension** (which dimension we tried to improve that cycle). This shows *which interventions improved which dimensions*. |
| **Run summary** | `evaluation_summary.txt` | Total ads generated, count meeting threshold (≥7.0), average overall score, max iterations per ad. |
| **Quality trend** | `iteration_quality_chart.png` | A line chart: x = cycle (or run), y = average quality score. Shows whether quality improves over cycles. Generated when matplotlib is available. |
| **Performance per token** | `ad_engine.metrics.performance_metrics` | Structure for `performance_per_token = avg_quality_score / token_cost`. Token cost is not auto-populated in v1; the module is in place for when usage/cost is recorded. |

## Where to Find Them

- **After a run:** All of the above (except performance_per_token with real cost) are written under `output/` by default.
  - `output/ads_dataset.json` — full ad copy, scores, iteration_history.
  - `output/evaluation_report.csv` — ad_id, overall_score, iteration_count, five dimension columns.
  - `output/evaluation_summary.txt` — text summary and pointer to the chart.
  - `output/iteration_quality_chart.png` — quality trend chart (if matplotlib installed).
- **Sample outputs:** `examples/generated_ad_samples.json` shows the shape of generated ads with evaluation scores (no iteration_history in that sample).

## How to Generate for a Demo

1. **CLI:** `./scripts/run_local.sh --num-ads 10 --max-iterations 6`  
   Then open `output/evaluation_summary.txt`, `output/evaluation_report.csv`, and `output/iteration_quality_chart.png`.

2. **Web UI:** Run `./scripts/run_web.sh`, start a run (e.g. 10 ads), then use the download links on the page for the same files.

## What “Quality Improvement” Means Here

- **Per ad:** We iterate until score ≥ 7.0 or max iterations. Each iteration targets the weakest dimension and re-evaluates. Improvement is visible in `iteration_history` (scores and targeted_dimension per cycle).
- **Across a run:** The run summary and chart show aggregate quality (e.g. average score, share above threshold). For multi-cycle experiments (e.g. running multiple batches and comparing), you would compare these aggregates and optionally plug in token cost for performance-per-token.
