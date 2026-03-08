# Brief Technical Writeup — Nerdy Autonomous Ad Engine

**1–2 page summary for submission.**

## What We Built

An autonomous pipeline that generates Facebook and Instagram ad copy for Varsity Tutors (Nerdy), evaluates each ad on five quality dimensions, and iteratively improves ads that fall below a 7.0/10 threshold by targeting the weakest dimension. The north star metric is **performance per token**: quality of outputs relative to API cost.

## Architecture

**Flow:** Structured brief → **Generator** (Gemini) → **Evaluator** (LLM-as-judge, 5 dimensions) → Decision: score ≥ 7.0? If yes, ad is accepted into the library; if no, **Iteration Engine** identifies the weakest dimension, runs a targeted improvement prompt, and re-evaluates. The loop runs until the ad meets threshold or a maximum iteration count (e.g. 6).

**Quality dimensions:** Clarity, Value Proposition, Call to Action, Brand Voice, Emotional Resonance. Each is scored 1–10 with a rationale and an optional confidence score. The overall score is a weighted average (Clarity and Value Proposition 25% each, Emotional Resonance 20%, CTA and Brand Voice 15% each). Ads below 7.0 are flagged and regenerated.

**Outputs:** Generated ads (primary text, headline, description, CTA), evaluation report (CSV/JSON with per-dimension scores and rationales), iteration history (which dimension was targeted each cycle), quality trend visualization, and a decision log documenting design choices.

## Key Design Choices

- **Single LLM (Gemini)** for both generation and evaluation in v1 to keep setup and cost low; the design allows swapping in a separate evaluator model for experiments.
- **Targeted regeneration** instead of full ad rewrite: we pass the weak dimension and its rationale into an improvement prompt so the model amends the ad rather than starting from scratch, reducing token use and preserving strong elements.
- **Failure handling:** Retries with exponential backoff on API calls; a hard cap on iterations per ad to avoid infinite loops; calibration script to run the evaluator on reference ads (good/bad) before scaling.
- **Reproducibility:** All runs are seeded (brief order, model generation) so results are reproducible for comparison and debugging.

## Deliverables Met

| Requirement | Delivered |
|-------------|-----------|
| Autonomous pipeline for FB/IG | Yes — `ad_engine` (generate → evaluate → iterate) |
| Evaluation framework (5 dimensions) | Yes — LLM-as-judge with rationales and confidence |
| Quality feedback loop | Yes — weakest-dimension targeting, configurable max iterations |
| 50+ ads with evaluation scores | Yes — `python -m ad_engine.cli run --num-ads 50` |
| Decision log | Yes — `docs/DECISION_LOG.md` |
| Evaluation report (JSON/CSV + trends) | Yes — `evaluation_report.csv`, `ads_dataset.json`, `evaluation_summary.txt`, quality chart |
| Code quality | 37 tests, one-command setup, modular layout, explicit limitations in decision log |

## How to Run

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
./scripts/run_local.sh              # CLI: 50 ads, 6 max iterations
./scripts/run_web.sh                 # Web UI at http://127.0.0.1:8080
```

Calibrate the evaluator on reference ads before a full run: `python scripts/calibrate_evaluator.py examples/reference_ads_sample.json`.

## Quality improvement metrics and visualizations

We track: **per-ad scores** (overall + 5 dimensions) in `evaluation_report.csv` and `ads_dataset.json`; **iteration history** per ad with `targeted_dimension` in `ads_dataset.json`; **run summary** in `evaluation_summary.txt`; **quality trend** chart in `output/iteration_quality_chart.png`; **ROI** (accepted per 1K tokens, cost) in `run_history.json` and the web Dashboard. After any run, see `output/` for these files.

## References

- **System design:** `docs/SYSTEM_DESIGN.md`
- **Decision log:** `docs/DECISION_LOG.md`
- **AI tools and prompts:** `docs/AI_TOOLS_AND_PROMPTS.md`
- **Generated samples:** `examples/generated_ad_samples.json`
