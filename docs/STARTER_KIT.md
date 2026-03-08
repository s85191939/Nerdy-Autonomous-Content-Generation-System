# Starter Kit: Autonomous Ad Generation

Model recommendations, evaluation workflow, and strategic guidance (per project PDF).

## Model recommendations

| Task | Recommended | Why |
|------|-------------|-----|
| Ad copy generation | **Gemini** | Strong creative writing, good at following brand voice constraints |
| Image generation (v2) | Imagen, Nano Banana, etc. | Brand-consistent image generation |

**API setup:** [Gemini API](https://ai.google.dev) — free tier available. Set `GEMINI_API_KEY` in your environment or `.env`.

## Evaluation workflow

The loop your system implements:

```
Brief → Generate Ad → Score (5 dimensions) → Above 7.0?
├─ Yes → Add to library
└─ No  → Identify weakest dimension
         → Targeted regeneration
         → Re-score
         → Track improvement
```

Key decisions (document in your decision log):

- How many regeneration attempts before giving up on a brief?
- Do you regenerate the whole ad or just the weak parts?
- How do you prevent the feedback loop from optimizing one dimension at the expense of others?
- When do you use expensive models vs cheap ones?

## The five dimensions

Every ad is scored on:

1. **Clarity** — Can you get the message in <3 seconds?
2. **Value Proposition** — Is the benefit specific and compelling?
3. **Call to Action** — Is the next step obvious and low-friction?
4. **Brand Voice** — Does it sound like Varsity Tutors?
5. **Emotional Resonance** — Does it tap into real motivation?

The five dimensions are scored 1–10 with a **rationale** and a **confidence** score (1–10) so the evaluator can signal when it’s uncertain. See **`examples/evaluation-sample.json`** for structure; the live evaluator also returns `confidence` per dimension.

## Getting started checklist

1. Study the reference ads provided via the Gauntlet/Nerdy Slack channel.
2. **Calibrate your evaluator** — run `python scripts/calibrate_evaluator.py` on reference ads (good/bad) so scores align with expectations before generating at scale.
3. Build your evaluator first — score the reference ads, calibrate.
4. Build a simple generator — one audience, one offer.
5. Wire the feedback loop — generate, evaluate, regenerate.
6. Scale to 50+ ads, track quality trends.
7. Write your decision log as you go, not at the end.

## Project setup (this repo)

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
python -m ad_engine.cli run --num-ads 50 --seed 42
```

See **README.md** for full setup and usage.
