# Demo Video / Live Walkthrough Guide

Use this as a script or outline for recording a demo or doing a live walkthrough.

## 1. Intro (30 sec)

- **What:** Autonomous ad engine for Facebook and Instagram (Varsity Tutors / Nerdy).
- **Goal:** Generate ad copy, score it on five dimensions, and iteratively improve ads below 7.0 until they meet the bar or hit max iterations.
- **North star:** Performance per token — quality per dollar of API spend.

## 2. Show the repo and docs (1 min)

- Open GitHub repo; point to **README** (setup, usage, rubric alignment).
- **docs/SYSTEM_DESIGN.md** — single place for architecture, quality dimensions, inputs/outputs.
- **docs/DECISION_LOG.md** — why we chose evaluation-first, single LLM, targeted regeneration, etc.

## 3. Run locally — CLI (2 min)

```bash
cd /path/to/Nerdy
export GEMINI_API_KEY="your-key"
./scripts/run_local.sh --num-ads 3 --max-iterations 2
```

- Explain: 3 ads for a quick demo; each ad is generated, scored, and if below 7.0 we target the weakest dimension and regenerate.
- When done, show **output/**:
  - **ads_dataset.json** — each ad with copy, scores, iteration_history (which dimension was targeted each cycle).
  - **evaluation_report.csv** — ad_id, overall_score, per-dimension scores.
  - **evaluation_summary.txt** — counts, average score, link to chart.
  - **iteration_quality_chart.png** — quality trend (if matplotlib installed).

## 4. Run locally — Web UI (1 min)

```bash
./scripts/run_web.sh
```

- Open http://127.0.0.1:8080.
- Set number of ads (e.g. 5), max iterations, seed. Click Run.
- Show progress bar and status; when done, show result summary and download links for the same output files.

## 5. Calibration (optional, 1 min)

- Run `python scripts/calibrate_evaluator.py examples/reference_ads_sample.json`.
- Explain: we score good/bad reference ads so the evaluator is calibrated before we generate at scale; reference ads from Slack can be dropped into a JSON file for this.

## 6. Key design choices (1 min)

- **Evaluation-first:** We built and calibrated the evaluator before scaling generation; the spec says “the system that surfaces only its best work wins.”
- **Targeted regeneration:** We don’t regenerate the whole ad each time; we pass the weak dimension and rationale so the model improves that dimension and keeps the rest.
- **Single LLM (Gemini)** for both generation and evaluation in v1 to keep setup simple; the design allows a separate evaluator for experiments.
- **Failure handling:** Retries with backoff on API calls; max iterations per ad so we don’t loop forever.

## 7. Wrap-up

- Point to **docs/TECHNICAL_WRITEUP.md** for a 1–2 page summary and **docs/AI_TOOLS_AND_PROMPTS.md** for prompts.
- Mention **generated ad samples** in **examples/generated_ad_samples.json** and **quality metrics** in **docs/QUALITY_IMPROVEMENT_METRICS.md**.

Total: ~7–8 minutes for a concise walkthrough; extend with more ads or deeper dives into code as needed.
