# Demo Video / Live Walkthrough Guide

Use this as a script or outline for recording a demo or doing a live walkthrough.

## 1. Intro (30 sec)

- **What:** Autonomous ad engine for Facebook and Instagram (Varsity Tutors / Nerdy).
- **Goal:** Generate ad copy, score it on five dimensions, and iteratively improve ads below 7.0 until they meet the bar or hit max iterations.
- **North star:** Performance per token — quality per dollar of API spend.

## 2. Show the repo and docs (1 min)

- Open GitHub repo; point to **README** (setup, usage, rubric alignment).
- **SUBMISSION_CHECKLIST.md** — all submission requirements at a glance.
- **DECISION_LOG.md** — why we chose evaluation-first, single LLM, targeted regeneration, etc.

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

- **Evaluation-first:** We built and calibrated the evaluator before scaling generation; the spec says "the system that surfaces only its best work wins."
- **Targeted regeneration:** We don't regenerate the whole ad each time; we pass the weak dimension and rationale so the model improves that dimension and keeps the rest.
- **Single LLM (Gemini)** for both generation and evaluation in v1 to keep setup simple; the design allows a separate evaluator for experiments.
- **Failure handling:** Retries with backoff on API calls; max iterations per ad so we don't loop forever.

## 7. Wrap-up

- Point to **TECHNICAL_WRITEUP.md** for a 1–2 page summary and **AI_TOOLS_AND_PROMPTS.md** for prompts.
- Mention **generated ad samples** in **generated_ad_samples.json** and **quality metrics** in **QUALITY_IMPROVEMENT_METRICS.md**.

Total: ~7–8 minutes for a concise walkthrough; extend with more ads or deeper dives into code as needed.

## Demo flow (printable)

- **Step 0** Prereqs: cd to repo; set GEMINI_API_KEY (or .env).
- **Step 1** Setup: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- **Step 2** Tests: `PYTHONPATH=. pytest tests/ -v` (expect 90+ passed).
- **Step 3** Quick CLI: `./scripts/run_local.sh --num-ads 3 --max-iterations 2`
- **Step 4** Outputs: `ls output/` — ads_dataset.json, evaluation_report.csv, evaluation_summary.txt, iteration_quality_chart.png, run_history.json
- **Step 5** Web UI: `./scripts/run_web.sh` then open http://127.0.0.1:8080; Run 5 ads; show Downloads
- **Step 6** Dashboard: Web UI → Dashboard (run history, ROI/tokens)
- **Step 7** Calibration (optional): `python scripts/calibrate_evaluator.py examples/reference_ads_sample.json`
- **Step 8** Full run: `python -m ad_engine.cli run --num-ads 50 --max-iterations 6 --seed 42`
- **Step 9** Submission docs: SUBMISSION_CHECKLIST.md, TECHNICAL_WRITEUP.md, DECISION_LOG.md, generated_ad_samples.json, QUALITY_IMPROVEMENT_METRICS.md
