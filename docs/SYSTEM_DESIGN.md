# System Design: Autonomous Ad Engine for Facebook & Instagram

**Unified technical design** aligned with the [Nerdy Autonomous Content Generation System](Nerdy-%20Autonomous%20Content%20Generation%20System.pdf) project spec, merging pre-search technical design and FAANG-style system design.

---

## 1. Challenge & North Star

| | |
|--|--|
| **Challenge** | Build an autonomous system that generates Facebook and Instagram ad copy, distinguishes good from bad, surfaces only its best work, and measurably improves over time. |
| **North star metric** | **Performance per token** — quality of generated ads per dollar of API spend. |
| **Domain** | Paid social ads for Facebook and Instagram only. No email, landing pages, or TikTok. |

This is a **systems engineering** challenge: generate → evaluate → iterate → improve, with minimal human intervention. Real ad engines produce many creatives; the system that surfaces only the best wins.

---

## 2. Design Goals & Non-Goals

**Goals**

1. Generate high-quality FB/IG ad copy from structured briefs.
2. Evaluate ad quality across five measurable dimensions.
3. Iteratively improve ads through a feedback loop (target weak dimension → regenerate → re-score).
4. Optimize token spend relative to ad quality (performance-per-token awareness).
5. Support batch generation at scale (50+ ads) with deterministic, reproducible runs.

**Non-Goals**

- Predict real campaign ROI without deployment.
- Replace human marketing strategy.
- Support channels beyond FB/IG.

---

## 3. Deliverables (Project Spec)

| Deliverable | Description |
|-------------|-------------|
| Autonomous ad copy pipeline | End-to-end generate → evaluate → iterate for FB/IG. |
| Evaluation framework | Five atomic quality dimensions, each independently scored. |
| Quality feedback loop | Demonstrate iterative improvement (e.g. 3+ cycles, 5+ for Excellent). |
| Generated ad library | 50+ ads with full evaluation scores. |
| Decision log | Documents *your* thinking and judgment calls. |
| Evaluation report | JSON/CSV plus summary with quality trends. |

---

## 4. Channel & Brand Context

**Channel:** Meta paid social (Facebook & Instagram). Reference ads and performance data are provided via the Gauntlet/Nerdy Slack channel.

**What works on Meta:** Authentic > polished; story-driven (pain → solution → proof → CTA); scroll-stopping hooks; social proof; emotional resonance for awareness.

**Ad anatomy:** Primary text (main copy, stops the scroll), Headline (bold, short), Description (often truncated), CTA button (e.g. Learn More, Sign Up).

**Brand: Varsity Tutors (Nerdy)**  
Voice: Empowering, knowledgeable, approachable, results-focused. Lead with outcomes, not features. Primary audience: SAT test prep — parents anxious about college admissions, high school students stressed about scores, families comparing prep options.

---

## 5. High-Level Architecture

```
Input Brief  →  Generator  →  Evaluator  →  Decision: Score ≥ 7.0?
                    ↑              │              │
                    │              │              ├─ Yes  →  Ad Library
                    │              │              └─ No   →  Identify weakest dimension
                    │              │                        →  Iteration Engine (targeted regeneration)
                    └──────────────┴──────────────────────→  Re-evaluate (loop until threshold or max iterations)
```

- **Generator:** Produces primary text, headline, description, CTA from a structured brief (audience, product, goal, tone). Uses an LLM with brand guidelines and format constraints.
- **Evaluator:** Scores each ad on five dimensions (1–10) with rationales and optional confidence. Aggregate score = weighted average.
- **Decision:** Accept (score ≥ 7.0) → add to library; else send to Iteration Engine.
- **Iteration Engine:** Targets the weakest dimension, triggers targeted regeneration (not full ad rewrite), then re-evaluates. Loop until threshold or max iterations (e.g. 6).
- **Ad Library:** Stores accepted ads, scores, iteration counts; persists to JSON (or DB at scale).
- **Metrics:** Tracks performance per token, quality trends, run summaries.

---

## 6. Quality Dimensions & Scoring

Every ad is scored on five dimensions (project spec). Threshold: **7.0/10** average to be publishable; below that, flag and regenerate.

| Dimension | What it measures | 1 (Bad) | 10 (Excellent) |
|-----------|------------------|---------|----------------|
| **Clarity** | Message understandable in &lt;3 seconds | Confusing, multiple messages | Crystal clear single takeaway |
| **Value Proposition** | Compelling benefit | Generic / feature-focused | Specific, differentiated (e.g. “raise SAT 200+ points”) |
| **Call to Action** | Next step clear and compelling | No CTA or vague | Specific, urgent, low-friction |
| **Brand Voice** | Sounds like the brand | Generic, could be anyone | Distinctly on-brand: empowering, knowledgeable, approachable |
| **Emotional Resonance** | Connects emotionally | Flat, purely rational | Taps into real motivation (parent worry, student ambition) |

**Quality scoring model (weighted average)**

| Dimension | Weight |
|-----------|--------|
| Clarity | 0.25 |
| Value Proposition | 0.25 |
| Emotional Resonance | 0.20 |
| Call to Action | 0.15 |
| Brand Voice | 0.15 |

**Explainability:** Evaluator returns a structured rationale per dimension; optional confidence score so the system knows when it’s uncertain. Calibrate against reference ads (good/bad) from Slack before scaling.

---

## 7. Inputs & Outputs

**Inputs**

- **Ad brief:** Audience segment, product/offer, campaign goal (awareness/conversion), tone.
- **Brand guidelines:** Voice, do’s and don’ts (as in project spec).
- **Reference ads:** Real Varsity Tutors ads and performance data (via Slack).
- **Evaluation config:** Dimension weights, quality threshold (e.g. 7.0).

**Outputs**

- **Generated ads:** Primary text, headline, description, CTA recommendation.
- **Evaluation report:** Scores per dimension with rationale, aggregate score, confidence.
- **Iteration log:** Changes per cycle, metrics before/after, which interventions improved which dimensions.
- **Quality trend:** Improvement trajectory across cycles (e.g. chart + summary).
- **Decision log:** Your reasoning for design choices.

---

## 8. Technical Architecture & Code Layout

**Suggested structure (project spec):**

```
generate/   — Ad copy generation from briefs
evaluate/   — Dimension scoring, LLM-as-judge, aggregation
iterate/    — Feedback loop, improvement strategies
storage/    — Ad library, evaluation logs
metrics/    — Performance per token, quality trends
output/     — Formatting, export, quality trend visualization
docs/       — Decision log, limitations, system design
```

**Technical specifications**

- Reproducibility: deterministic with seeds.
- Scale: 50+ ads generated and evaluated.
- Quality threshold: 7.0/10 minimum.
- Run locally (API keys acceptable); no real PII in generated content; document rate limits and cost.

**Models:** Ad copy generation: Gemini (recommended). Images (v2): Imagen, etc.

---

## 9. Failure Handling

| Risk | Safeguard |
|------|-----------|
| Infinite regeneration | Max iterations per ad (e.g. 6); then mark as not accepted and keep best version. |
| Evaluator drift | Periodic calibration against reference ads (good/worst); run calibration script before scaling. |
| Repetitive outputs (mode collapse) | Documented for future diversity constraint; iteration limits reduce runaway similarity. |
| API/network failures | Retries with exponential backoff on generator and evaluator calls. |

---

## 10. Scalability & Experiments

**Scalability:** Batch generation (e.g. 50+ ads per run); modular services so generator, evaluator, and iteration engine can be scaled or parallelized independently. Context management: each LLM call sees only system prompt + single user message (no cross-ad context) to keep cost and behavior predictable.

**Experimentation framework**

- Single vs multi-LLM evaluation (reliability of scores).
- Full regeneration vs targeted edits (which improves quality faster per token).
- Cheap vs expensive model (performance per token).

---

## 11. Success Criteria & Code Quality (Project Spec)

**Success criteria**

| Category | Metric | Target |
|----------|--------|--------|
| Coverage | Ads with full evaluation | 50+ |
| Coverage | Dimensions | 5, independently measured |
| Quality | Ads meeting 7.0/10 | Majority of final output |
| Improvement | Quality gain over cycles | Measurable lift across 3+ (5+ for Excellent) |
| Explainability | Evaluations with rationales | 100% |
| Documentation | Decision log with your reasoning | Complete and honest |

**Code quality**

- Clear modular structure; one-command setup (e.g. `requirements.txt`); concise README.
- ≥10 unit/integration tests (15+ for Excellent); deterministic behavior (seeds).
- Decision log explaining what you tried, what worked, what didn’t, and *why*; explicit limitations.

---

## 12. Evaluation Criteria (Rubric Summary)

| Area | Weight | Focus |
|------|--------|--------|
| Quality Measurement & Evaluation | 25% | Can the system tell good ads from bad? (dimensions, calibration, threshold, confidence) |
| System Design & Architecture | 20% | Is the system well-built and resilient? (modularity, failure handling, tests, context management) |
| Iteration & Improvement | 20% | Does quality measurably improve? (cycles, which interventions helped, performance-per-token awareness) |
| Speed of Optimization | 15% | How efficiently does it iterate? (batch 50+, minimal human intervention, smart resource use) |
| Documentation & Individual Thinking | 20% | Can we see your mind at work? (decision log WHY, failed approaches, honest limitations) |

Automatic deductions apply for no demo, can’t run, &lt;50 ads, no evaluation scores, no iteration, or no decision log. Bonus points for self-healing, multi-model orchestration, performance-per-token tracking, quality trend visualization, and competitive intelligence.

---

## 13. Scope Variants & Future Work

**v1 (Ad Copy Pipeline):** Text-only generation and evaluation; 5 dimensions; feedback loop with targeted regeneration; 7.0 threshold; 50+ ads; 3+ (5+ for Excellent) iteration cycles. Single LLM for generation and evaluation is acceptable.

**v2 (Multi-Modal):** v1 + image generation, visual evaluation, A/B variants, multi-model orchestration.

**v3 (Autonomous Ad Engine):** v2 + self-healing feedback loops, quality ratchet, performance-per-token tracking, agentic orchestration (e.g. researcher, writer, editor, evaluator, optimizer), competitive intelligence (e.g. Meta Ad Library).

---

## 14. Reference Documents

- **Project spec:** [Nerdy- Autonomous Content Generation System.pdf](Nerdy-%20Autonomous%20Content%20Generation%20System.pdf)
- **Pre-search technical design:** [autonomous_ad_engine_presearch_design.pdf](autonomous_ad_engine_presearch_design.pdf)
- **FAANG-style system design:** [faang_style_autonomous_ad_engine_sysdesign.pdf](faang_style_autonomous_ad_engine_sysdesign.pdf)
- **Starter kit:** [STARTER_KIT.md](STARTER_KIT.md) — model recommendations, evaluation workflow, getting started.
- **Decision log:** [DECISION_LOG.md](DECISION_LOG.md) — design choices, tradeoffs, failed approaches, limitations.
