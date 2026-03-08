# Documentation of AI Tools and Prompts

Submission requirement: document AI tools and prompts used.

## AI Tools

| Tool | Role | Where used |
|------|------|------------|
| **Google Gemini API** (`google-generativeai`, model `gemini-1.5-flash`) | Ad copy generation and LLM-as-judge evaluation | `ad_engine/generate/generator.py`, `ad_engine/evaluate/dimension_scorer.py` |

- **Generation:** One API call per ad (or per improvement step). Input: system prompt (brand + format) + user message (brief or improvement instruction). Output: JSON with `primary_text`, `headline`, `description`, `cta`.
- **Evaluation:** One API call per ad. Input: system prompt (rubrics + confidence) + user message (ad JSON). Output: JSON with per-dimension `score`, `rationale`, `confidence`.

No other AI tools (e.g. OpenAI, Claude) are used in the default pipeline. The design allows swapping in a different model for the evaluator for experiments (see `docs/EXPERIMENTS.md`).

## Prompts

### 1. Ad generation (system)

**Location:** `ad_engine/generate/prompt_templates.py` — `AD_GENERATION_SYSTEM`, `DEFAULT_BRAND_VOICE`

**Purpose:** Define the copywriter role, brand voice (Varsity Tutors / Nerdy, SAT audience), and Meta ad format. Instruct the model to output only valid JSON with keys `primary_text`, `headline`, `description`, `cta`.

**Key content:**
- Brand: Varsity Tutors (Nerdy). Voice: Empowering, knowledgeable, approachable, results-focused. Lead with outcomes, not features.
- Primary audience: SAT test prep — parents, high school students, families comparing prep.
- Meta format: Primary text (hook ~125 chars, story-driven), headline (5–8 words, benefit-driven), description (optional), CTA (Learn More / Sign Up / Get Started).

### 2. Ad generation (user — from brief)

**Location:** `ad_engine/generate/prompt_templates.py` — `AD_GENERATION_USER`

**Template:**  
`Audience: {audience}\nProduct/offer: {product}\nGoal: {goal}\nTone: {tone}\n\nGenerate one Facebook/Instagram ad. Return only a single JSON object with keys: primary_text, headline, description, cta.`

**Example inputs:** audience = "Parents of high school juniors", product = "SAT tutoring program", goal = "conversion", tone = "reassuring, results-focused".

### 3. Ad improvement (user — targeted regeneration)

**Location:** `ad_engine/generate/prompt_templates.py` — `IMPROVEMENT_USER`

**Template:**  
`Previous ad:\n{ad_json}\n\nEvaluation: The ad scored below 7.0. Weakest dimension: {weak_dimension}.\nRationale: {rationale}\n\nImprove the ad specifically to strengthen {weak_dimension}. Keep primary_text, headline, description, and cta. Return only the improved ad as a single JSON object with keys: primary_text, headline, description, cta.`

**Purpose:** After evaluation, if score < 7.0, we pass the ad, the weakest dimension name, and the evaluator’s rationale so the model amends the ad instead of rewriting from scratch.

### 4. Evaluation (system)

**Location:** `ad_engine/evaluate/dimension_scorer.py` — `EVALUATION_SYSTEM`

**Purpose:** Define the evaluator role and the five dimensions (1–10 scale), plus confidence (1–10). Require a single JSON object with keys `clarity`, `value_proposition`, `cta`, `brand_voice`, `emotional_resonance`; each value is `{ "score", "rationale", "confidence" }`.

**Dimensions (abbreviated):**
- clarity — understandable in &lt;3 seconds  
- value_proposition — specific, compelling benefit  
- cta — clear, compelling next step  
- brand_voice — Varsity Tutors: empowering, knowledgeable, approachable  
- emotional_resonance — connects emotionally (e.g. parent worry, test anxiety)

### 5. Evaluation (user)

**Location:** `ad_engine/evaluate/dimension_scorer.py` — `EVALUATION_USER`

**Template:**  
`Ad to evaluate (JSON):\n{ad_json}\n\nReturn one JSON object with keys clarity, value_proposition, cta, brand_voice, emotional_resonance. Each value: {"score": 1-10, "rationale": "...", "confidence": 1-10}.`

### 6. Improvement hints (fallback rationale)

**Location:** `ad_engine/iterate/improvement_strategies.py` — `IMPROVEMENT_STRATEGIES`

When the evaluator does not return a usable rationale for the weak dimension, we pass a short hint per dimension, e.g.:
- clarity: single clear takeaway, understandable in &lt;3 seconds  
- value_proposition: specific outcome (score improvement, time saved)  
- cta: specific, low-friction (e.g. “Start your free practice test”)  
- brand_voice: Varsity Tutors tone  
- emotional_resonance: parent worry, student ambition, test anxiety  

These are not full prompts; they are one-line hints injected into the improvement user message when rationale is missing.
