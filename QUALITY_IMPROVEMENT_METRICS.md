# Quality Improvement Metrics and Visualizations

**Submission requirement:** Quality improvement metrics and visualizations.

## What We Track

| Metric | Where | Description |
|--------|--------|-------------|
| **Per-ad scores** | `output/ads_dataset.json`, `output/evaluation_report.csv` | Overall score (1–10) and per-dimension scores (clarity, value_proposition, cta, brand_voice, emotional_resonance) for every generated ad. |
| **Iteration history** | `output/ads_dataset.json` → `iteration_history` per ad | For each improvement cycle: iteration number, overall_score, dimension scores, and **targeted_dimension** (which dimension was targeted for regeneration). Shows *which interventions improved which dimensions*. |
| **Run summary** | `output/evaluation_summary.txt` | Total ads generated, count meeting threshold (≥7.0), average overall score, max iterations per ad. v3: Quality ratchet line (best avg so far, floor). |
| **Quality trend chart** | `output/iteration_quality_chart.png` | Plot of average quality score over run cycles (when multiple runs exist). Generated if matplotlib is installed. |
| **ROI / performance per token** | `output/run_history.json`, Web UI → Dashboard | Per run: total tokens, estimated cost (USD), accepted ads per 1K tokens, score per dollar. |

## How to Generate

After running the pipeline:

1. Launch the web UI: `./scripts/run_web.sh` → http://127.0.0.1:8080
2. Enter your brief, set num_ads to 50, and click **Generate ads**

The `output/` directory will contain:

- `ads_dataset.json` — full ad copy, scores, dimensions (rationales, confidence), iteration_history
- `evaluation_report.csv` — ad_id, overall_score, iteration_count, per-dimension scores
- `evaluation_summary.txt` — counts, threshold %, average score, quality ratchet
- `iteration_quality_chart.png` — quality trend (if matplotlib available)
- `run_history.json` — append-only log of each run (tokens, cost, ROI metrics)

The **Web UI** (http://127.0.0.1:8080) Dashboard tab shows run history and ROI at a glance.

## Sample Summary (from a 5-ad run)

```
Evaluation Summary
==================
Total ads generated: 5
Ads meeting quality threshold (>= 7.0): 5 (100.0%)
Average overall score: 8.54
Max iterations per ad: 3

Quality trend: See iteration_quality_chart.png for cycle-over-cycle average score.
Iteration log: Each ad in ads_dataset.json includes 'iteration_history' with scores and targeted_dimension per cycle.
```

See [TECHNICAL_WRITEUP.md](TECHNICAL_WRITEUP.md) § "Quality improvement metrics and visualizations" for more detail.
