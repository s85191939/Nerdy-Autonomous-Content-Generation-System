# Nerdy Autonomous Content Generation System

Autonomous Facebook & Instagram ad copy generation engine with evaluation and iterative improvement. Built for the Gauntlet/Nerdy challenge.

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

Generate and evaluate 50+ ads with iteration (default up to 6 cycles per ad for 5+ cycle demonstration):

```bash
python -m ad_engine.cli run --num-ads 50 --max-iterations 6 --seed 42
```

**Before running at scale**, calibrate the evaluator on reference ads (Excellent rubric: *Calibrated against best/worst reference ads*):

```bash
python scripts/calibrate_evaluator.py examples/reference_ads_sample.json
# Or your own JSON from Gauntlet/Nerdy Slack reference ads
```

Export reports and visualizations:

```bash
python -m ad_engine.cli export --output-dir output/
```

Run tests (**15+ unit/integration tests**, deterministic):

```bash
PYTHONPATH=. pytest tests/ -v
```

### Web interface

Run the web UI for a simpler workflow (configure run, see progress, download outputs):

```bash
./scripts/run_web.sh
```

Then open **http://127.0.0.1:8080**. Set `GEMINI_API_KEY` in `.env` (or use the **OpenRouter** section in the form for free models).

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
- **System Design (20%):** Modular architecture, **failure detection and recovery** (retries with backoff), one-command setup, **15+ tests**, deterministic. **Context management** documented in Decision log §11.
- **Iteration (20%):** **5+ iteration cycles** (default `--max-iterations 6`), measurable gains, **which interventions improved which dimensions** in `iteration_history` (targeted_dimension), **performance-per-token awareness** (see `ad_engine.metrics` and Dashboard).
- **Speed (15%):** Batch generation 50+ ads, minimal human intervention. **Smart resource allocation:** single model (Gemini Flash) for both generation and evaluation to reduce cost.
- **Documentation (20%):** Decision log with **WHY**; **failed approaches and where it breaks** (§12); honest limitations; independent thinking.
- **Bonus:** Quality trend visualization (+2); ROI/token awareness (+2). See `output/` and Dashboard after a run.

## Docs

We keep **6 docs**; the rest is in README and code.

- [**Deliverables**](docs/DELIVERABLES.md) — Checklist (pipeline, evaluation, loop, 50+ ads, decision log, evaluation report) + v1 spec alignment + v2 future.
- [**Decision log**](docs/DECISION_LOG.md) — Design choices, tradeoffs, limitations, failed approaches. *Matters as much as the output.*
- [**System design**](docs/SYSTEM_DESIGN.md) — Canonical design (spec + pre-search + FAANG-style).
- [**Technical writeup**](docs/TECHNICAL_WRITEUP.md) — 1–2 page summary, architecture, quality metrics, how to run.
- [**AI tools and prompts**](docs/AI_TOOLS_AND_PROMPTS.md) — Models and prompts used.
- [**Demo walkthrough**](docs/DEMO_WALKTHROUGH.md) — Script for demo video or live walkthrough.

**What we're evaluated on:** Problem decomposition, taste and judgment, creative agency, systems thinking, iteration methodology, and the decision log. This repo addresses each: five measurable dimensions and a generate→evaluate→improve loop (decomposition); rubrics and calibration (taste); working PoC with fallbacks (agency); retries and failure handling (systems); targeted regeneration and iteration_history (methodology); DECISION_LOG documents why and where it breaks.

- **All PDFs** are in `docs/`: project spec, pre-search design, FAANG-style sysdesign.

### Submission checklist

| Requirement | Location |
|-------------|----------|
| **Deliverables checklist** (pipeline, evaluation, feedback loop, 50+ ads, decision log, evaluation report) | [docs/DELIVERABLES.md](docs/DELIVERABLES.md) |
| Code repository | GitHub (see top of README) |
| Brief technical writeup (1–2 pages) | [docs/TECHNICAL_WRITEUP.md](docs/TECHNICAL_WRITEUP.md) |
| Documentation of AI tools and prompts | [docs/AI_TOOLS_AND_PROMPTS.md](docs/AI_TOOLS_AND_PROMPTS.md) |
| Demo video or live walkthrough | Use [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) as script |
| Generated ad samples with evaluation scores | [examples/generated_ad_samples.json](examples/generated_ad_samples.json) |
| Quality improvement metrics and visualizations | TECHNICAL_WRITEUP §Quality improvement; outputs in `output/` after a run |
| Decision log | [docs/DECISION_LOG.md](docs/DECISION_LOG.md) |

## License

MIT
