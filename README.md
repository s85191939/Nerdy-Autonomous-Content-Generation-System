# Nerdy Autonomous Content Generation System

Autonomous Facebook & Instagram ad copy generation engine with evaluation and iterative improvement. Built for the Gauntlet/Nerdy challenge.

## Submission requirements (at a glance)

All submission requirements are at the **repository root** so reviewers can see everything on first glance:

| Requirement | Location |
|-------------|----------|
| **Submission checklist** (all 7 items) | [**SUBMISSION_CHECKLIST.md**](SUBMISSION_CHECKLIST.md) |
| Code repository | This repo; `pip install -r requirements.txt` then `./scripts/run_web.sh` → http://127.0.0.1:8080 |
| Brief technical writeup (1–2 pages) | [TECHNICAL_WRITEUP.md](TECHNICAL_WRITEUP.md) |
| Documentation of AI tools and prompts | [AI_TOOLS_AND_PROMPTS.md](AI_TOOLS_AND_PROMPTS.md) |
| Demo video or live walkthrough | Live demo / recorded walkthrough |
| Generated ad samples with evaluation scores | [generated_ad_samples.json](generated_ad_samples.json) |
| Quality improvement metrics and visualizations | [QUALITY_IMPROVEMENT_METRICS.md](QUALITY_IMPROVEMENT_METRICS.md) and `output/` after a run |
| Decision log (YOUR choices and reasoning) | [DECISION_LOG.md](DECISION_LOG.md) |

---

## Overview

- **Generate** ad copy from structured briefs (Gemini).
- **Evaluate** each ad on 5 dimensions (Clarity, Value Proposition, CTA, Brand Voice, Emotional Resonance).
- **Iterate** on ads below 7.0/10 via targeted regeneration.
- **Track** performance per token and quality trends.

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Set at least one API key (used in fallback order so the product keeps working):

```bash
export GEMINI_API_KEY="your-key"   # or add to .env — tried first
```

**Fallback (automatic):** If Gemini fails (quota, 401, etc.), the app tries **OpenRouter** then **OpenAI** so you get ads instead of errors. Set any of:

```bash
export OPENROUTER_API_KEY="your-openrouter-key"   # free models at openrouter.ai/keys
export OPENROUTER_MODEL="openrouter/free"         # optional
export OPENAI_API_KEY="your-openai-key"          # optional third fallback
```

Priority: **Gemini → OpenRouter → OpenAI**. Only configured backends are used; at least one required.

## Usage

Launch the web UI:

```bash
./scripts/run_web.sh
```

Then open **http://127.0.0.1:8080**. Set `GEMINI_API_KEY` in `.env` (or use the **OpenRouter** section in the form for free models).

From the web UI you can:
- Enter a creative brief (audience, product, goal, tone, brand name)
- Configure number of ads, quality threshold, max iterations
- Watch real-time progress as ads are generated, evaluated, and improved
- Browse results with per-dimension scores and iteration history
- Download exports (JSON, CSV, quality chart)
- View all past campaigns in the Dashboard

**Before running at scale**, calibrate the evaluator on reference ads (Excellent rubric: *Calibrated against best/worst reference ads*):

```bash
python scripts/calibrate_evaluator.py examples/reference_ads_sample.json
```

Run tests (**80+ unit/integration tests**, deterministic):

```bash
PYTHONPATH=. pytest tests/ -v
```

### Deploy as a web app

Deploy the web UI to a host that sets `PORT` (e.g. Render, Railway, Fly.io):

- **Procfile (Render / Heroku):** `web: gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 web.app:app`  
  Set **Root Directory** to the repo root. Add env vars: `GEMINI_API_KEY` (and optionally `OPENROUTER_API_KEY`, `OPENAI_API_KEY`).

- **Docker:**  
  `docker build -t nerdy-web . && docker run -p 8080:8080 -e GEMINI_API_KEY=your-key nerdy-web`  
  Open http://localhost:8080. For production, set `PORT` in the environment and use your host’s default port.

Users must set an API key in the UI (or you configure env vars on the host) for ad generation to work.

## Project Structure

```
ad_engine/
  generate/     # Ad copy generation from briefs
  evaluate/     # LLM-as-judge, 5 dimensions, aggregation
  iterate/      # Feedback loop, weak-dimension targeting
  storage/      # Ad library, evaluation logs
  metrics/      # Performance per token, quality trends
  output/       # Export CSV/JSON, visualizations
docs/           # Decision log, limitations
tests/          # Unit and integration tests
output/         # Generated reports (gitignored)
```

## Success Criteria

| Metric              | Target   |
|---------------------|----------|
| Ads generated       | ≥ 50     |
| Quality threshold    | ≥ 7.0    |
| Iteration cycles     | ≥ 3 (5+ for Excellent) |
| Evaluation dimensions| 5        |
| Reproducibility      | Seed-based|

## Rubric alignment (full points)

- **Quality (25%):** 5 dimensions with clear rubrics, LLM-as-judge with rationales, **confidence scoring** per dimension, 7.0+ threshold, dimension weights documented. **Calibrate** with `scripts/calibrate_evaluator.py` and reference ads from Slack.
- **System Design (20%):** Modular architecture, **failure detection and recovery** (retries with backoff), one-command setup, **80+ tests**, deterministic. **Context management** documented in Decision log §11.
- **Iteration (20%):** **5+ iteration cycles** (default max iterations: 6), measurable gains, **which interventions improved which dimensions** in `iteration_history` (targeted_dimension), **performance-per-token awareness** (see `ad_engine.metrics` and Dashboard).
- **Speed (15%):** Batch generation 50+ ads, minimal human intervention. **Smart resource allocation:** single model (Gemini Flash) for both generation and evaluation to reduce cost.
- **Documentation (20%):** Decision log with **WHY**; **failed approaches and where it breaks** (§13); honest limitations; independent thinking.
- **Bonus:** Quality trend visualization (+2); ROI/token awareness (+2). See `output/` and Dashboard after a run.

## Docs

All submission docs are at repo root: [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md), [TECHNICAL_WRITEUP.md](TECHNICAL_WRITEUP.md), [AI_TOOLS_AND_PROMPTS.md](AI_TOOLS_AND_PROMPTS.md), [generated_ad_samples.json](generated_ad_samples.json), [QUALITY_IMPROVEMENT_METRICS.md](QUALITY_IMPROVEMENT_METRICS.md), [DECISION_LOG.md](DECISION_LOG.md).

## License

MIT
