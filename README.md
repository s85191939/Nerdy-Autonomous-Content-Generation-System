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

Set your API key:

```bash
export GEMINI_API_KEY="your-key"   # or add to .env
```

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

Then open **http://127.0.0.1:8080**. Set `GEMINI_API_KEY` in `.env` or your environment first.

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
- **Iteration (20%):** **5+ iteration cycles** (default `--max-iterations 6`), measurable gains, **which interventions improved which dimensions** in `iteration_history` (targeted_dimension), **performance-per-token awareness** (see `ad_engine.metrics.performance_metrics` and [Rate limits and cost](docs/RATE_LIMITS_AND_COST.md)).
- **Speed (15%):** Batch generation 50+ ads, minimal human intervention. **Smart resource allocation:** single model (Gemini Flash) for both generation and evaluation to reduce cost.
- **Documentation (20%):** Decision log with **WHY**; **failed approaches and where it breaks** (§12); honest limitations; independent thinking.
- **Bonus:** Quality trend visualization (+2); ROI/token awareness (+2). See [EXPERIMENTS.md](docs/EXPERIMENTS.md) for performance-per-token tracking options.

## Docs

- [System Design](docs/SYSTEM_DESIGN.md) — **Canonical** combined design (spec + pre-search + FAANG-style); start here.
- [Technical Design](docs/TECHNICAL_DESIGN.md) — Short pointer to SYSTEM_DESIGN and PDFs.
- [Decision Log](docs/DECISION_LOG.md) — design choices and tradeoffs.
- [Starter Kit](docs/STARTER_KIT.md) — model recommendations, evaluation workflow, getting started (per project spec).
- [Experiments](docs/EXPERIMENTS.md) — how to run single vs multi-LLM, full vs targeted regeneration, and cheap vs expensive model experiments.
- [Rate limits and cost](docs/RATE_LIMITS_AND_COST.md) — API rate limits and cost considerations.
- **All PDFs** are in `docs/`: project spec, pre-search design, FAANG-style sysdesign.

### Submission checklist

| Requirement | Location |
|-------------|----------|
| Code repository | GitHub (see top of README) |
| Brief technical writeup (1–2 pages) | [docs/TECHNICAL_WRITEUP.md](docs/TECHNICAL_WRITEUP.md) |
| Documentation of AI tools and prompts | [docs/AI_TOOLS_AND_PROMPTS.md](docs/AI_TOOLS_AND_PROMPTS.md) |
| Demo video or live walkthrough | Use [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) as script |
| Generated ad samples with evaluation scores | [examples/generated_ad_samples.json](examples/generated_ad_samples.json) |
| Quality improvement metrics and visualizations | [docs/QUALITY_IMPROVEMENT_METRICS.md](docs/QUALITY_IMPROVEMENT_METRICS.md); outputs in `output/` after a run |
| Decision log | [docs/DECISION_LOG.md](docs/DECISION_LOG.md) |

## License

MIT
