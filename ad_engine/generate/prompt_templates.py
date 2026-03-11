"""Prompt templates for ad generation and brand voice.

Calibrated to Meta ad copy structure and inspired by proven patterns from
50 high-performing Facebook ad examples across major brands.
"""

# ---------------------------------------------------------------------------
# Meta ad structure reference (used across prompts)
# ---------------------------------------------------------------------------
META_AD_STRUCTURE = """
## Exact Meta Ad Copy Structure

PRIMARY TEXT (above the image):
- The first line is everything — hook or lose them.
- First line MUST be ≤125 characters (the visible portion before "...See More").
- After the hook, develop with: pain → solution → proof → CTA.
- Keep paragraphs short (1-2 sentences). Use line breaks for scannability.
- Embed social proof naturally (numbers, testimonials, results).
- Strategic emoji use is acceptable but not required.

HEADLINE (bold text below the image):
- 5–8 words maximum. Benefit-driven, NOT feature-driven.
- Should communicate the core value proposition at a glance.
- Action-oriented language preferred.

DESCRIPTION (smaller text below headline):
- Optional reinforcement — often truncated on mobile, so don't rely on it.
- Use to add a secondary benefit or urgency element.

CTA BUTTON:
- Must match the funnel stage:
  • Awareness → "Learn More"
  • Consideration → "Sign Up" or "Get Started"
  • Conversion → "Shop Now", "Book Now", or "Get Offer"
"""

# ---------------------------------------------------------------------------
# Proven hook types (from analysis of 50 high-performing FB ads)
# ---------------------------------------------------------------------------
HOOK_PATTERNS = """
## Proven First-Line Hook Types (pick ONE per ad):

1. QUESTION HOOK — Ask a pain-point question the audience can't ignore.
   Example: "Is your child's SAT score holding them back?"
2. STAT / NUMBER HOOK — Lead with a specific, compelling number.
   Example: "Students who prep score 200+ points higher on average."
3. STORY / TESTIMONIAL HOOK — Open with a mini success story.
   Example: "My daughter went from 1050 to 1400 in 8 weeks."
4. BOLD CLAIM HOOK — Make a confident, specific promise.
   Example: "We guarantee a 200-point score increase — or your money back."
5. PAIN POINT HOOK — Name the exact frustration the audience feels.
   Example: "College rejection letters are brutal. Don't let scores be the reason."
6. CURIOSITY GAP HOOK — Tease a result that demands the reader learn more.
   Example: "The 15-minute daily habit that raised her SAT score by 300 points."
"""

DEFAULT_BRAND_VOICE = """
Brand: Varsity Tutors (Nerdy)
Voice: Empowering, knowledgeable, approachable, results-focused.
- Lead with outcomes, not features.
- Confident but not arrogant. Expert but not elitist.
- Meet people where they are.
Primary audience: SAT test prep — parents anxious about college admissions, high school students stressed about scores.
"""

AD_GENERATION_SYSTEM = (
    "You are an expert Facebook and Instagram ad copywriter for Varsity Tutors (Nerdy), "
    "an SAT/test prep tutoring brand.\n"
    + DEFAULT_BRAND_VOICE
    + META_AD_STRUCTURE
    + HOOK_PATTERNS
    + """
## Creative Best Practices (from top-performing Meta ads):
- Lead with a specific, measurable outcome (e.g. "200+ point increase").
- Use social proof: real numbers, student counts, success rates.
- Keep the emotional arc tight: pain → solution → proof → CTA.
- Write at an 8th-grade reading level. Short sentences win.
- Every word must earn its place — cut filler ruthlessly.

Output valid JSON only, with keys: primary_text, headline, description, cta."""
)

AD_GENERATION_USER = """Audience: {audience}
Product/offer: {product}
Goal: {goal}
Tone: {tone}
{creative_angle_suffix}
Generate one Facebook/Instagram ad. Return only a single JSON object with keys: primary_text, headline, description, cta."""

VARIANT_ANGLES = [
    "Use a QUESTION HOOK for the first line (e.g. 'Is your child's SAT score holding them back?'). The question must name a specific pain point the audience feels.",
    "Use a STAT / NUMBER HOOK for the first line (e.g. 'Students who prep score 200+ points higher on average.'). Lead with a concrete, specific number.",
    "Use a STORY / TESTIMONIAL HOOK for the first line (e.g. 'My daughter went from 1050 to 1400 in 8 weeks.'). Open with a real-feeling success story in first person.",
    "Use a BOLD CLAIM HOOK for the first line (e.g. 'We guarantee a 200-point score increase.'). Make a confident, specific promise.",
    "Use a PAIN POINT HOOK for the first line (e.g. 'College rejection letters are brutal.'). Name the exact frustration or fear the audience feels.",
    "Use a CURIOSITY GAP HOOK for the first line (e.g. 'The 15-minute daily habit that raised her SAT score by 300 points.'). Tease a result that demands the reader learn more.",
]


# --- Builder functions for custom briefs ---


def _is_custom_brief(brief: dict = None) -> bool:
    """Return True if brief represents a custom (non-Varsity Tutors) brand."""
    return brief is not None and bool(brief.get("brand_name"))


def build_brand_voice(brief: dict = None) -> str:
    """Return brand voice block — dynamic for custom briefs, default for Varsity Tutors."""
    if not _is_custom_brief(brief):
        return DEFAULT_BRAND_VOICE
    brand_name = brief.get("brand_name", "Brand")
    tone = brief.get("tone", "professional, engaging")
    audience = brief.get("audience", "target audience")
    goal = brief.get("goal", "engagement")
    return f"""
Brand: {brand_name}
Voice: {tone}.
- Lead with outcomes, not features.
- Confident but not arrogant.
- Meet people where they are.
Primary audience: {audience} — {goal}.
"""


def _build_custom_hook_patterns(brief: dict) -> str:
    """Return hook patterns customized for the brief's product and audience."""
    product = brief.get("product", "product")
    audience = brief.get("audience", "target audience")
    return f"""
## Proven First-Line Hook Types (pick ONE per ad):

1. QUESTION HOOK — Ask a pain-point question {audience} can't ignore.
2. STAT / NUMBER HOOK — Lead with a specific, compelling number about {product}.
3. STORY / TESTIMONIAL HOOK — Open with a mini success story from a real {audience} persona.
4. BOLD CLAIM HOOK — Make a confident, specific promise about {product}.
5. PAIN POINT HOOK — Name the exact frustration {audience} feels.
6. CURIOSITY GAP HOOK — Tease a result related to {product} that demands the reader learn more.
"""


def build_ad_generation_system(brief: dict = None) -> str:
    """Return system prompt for ad generation — dynamic for custom briefs."""
    if not _is_custom_brief(brief):
        return AD_GENERATION_SYSTEM
    brand_name = brief.get("brand_name", "Brand")
    product = brief.get("product", "product")
    brand_voice = build_brand_voice(brief)
    hook_patterns = _build_custom_hook_patterns(brief)
    return f"""You are an expert Facebook and Instagram ad copywriter for {brand_name}, promoting {product}.

{brand_voice}
{META_AD_STRUCTURE}
{hook_patterns}
## Creative Best Practices (from top-performing Meta ads):
- Lead with a specific, measurable outcome relevant to {product}.
- Use social proof: real numbers, customer counts, success rates.
- Keep the emotional arc tight: pain → solution → proof → CTA.
- Write at an 8th-grade reading level. Short sentences win.
- Every word must earn its place — cut filler ruthlessly.

Output valid JSON only, with keys: primary_text, headline, description, cta."""


def build_variant_angles(brief: dict = None) -> list:
    """Return variant angles — dynamic for custom briefs, default SAT angles otherwise."""
    if not _is_custom_brief(brief):
        return VARIANT_ANGLES
    product = brief.get("product", "product")
    audience = brief.get("audience", "target audience")
    return [
        f"Use a QUESTION HOOK for the first line — ask a specific pain-point question that {audience} can't ignore.",
        f"Use a STAT / NUMBER HOOK for the first line — lead with a concrete, compelling number about {product}.",
        f"Use a STORY / TESTIMONIAL HOOK for the first line — open with a mini success story about {product} from a real {audience} persona.",
        f"Use a BOLD CLAIM HOOK for the first line — make a confident, specific promise about {product}.",
        f"Use a PAIN POINT HOOK for the first line — name the exact frustration or fear that {audience} feels.",
        f"Use a CURIOSITY GAP HOOK for the first line — tease a result related to {product} that demands the reader learn more.",
    ]

IMPROVEMENT_USER = """Previous ad:
{ad_json}

Evaluation: The ad scored below 7.0. Weakest dimension: {weak_dimension}.
Rationale: {rationale}

Improve the ad specifically to strengthen {weak_dimension}. Keep primary_text, headline, description, and cta. Return only the improved ad as a single JSON object with keys: primary_text, headline, description, cta."""

COMPETITOR_PATTERNS_SYSTEM = "You analyze FB/IG ad copy and extract hook patterns, CTAs, and tone angles."
COMPETITOR_PATTERNS_USER = "Analyze these ads. Return ONLY one JSON: hooks (array), ctas (array), tone_angles (array). Ads: {ads_json}"
REWRITE_AS_BRAND_SYSTEM = "You rewrite competitor ads into Varsity Tutors (Nerdy) brand. Keep hook structure and CTA type."
REWRITE_AS_BRAND_USER = "Rewrite in Varsity Tutors brand. Return only JSON: primary_text, headline, description, cta. Ad: {ad_json}"
REFERENCE_PATTERNS_SNIPPET = " Proven patterns: hooks {hooks}, CTAs {ctas}, angles {tone_angles}. Fit our brand into these where appropriate."
