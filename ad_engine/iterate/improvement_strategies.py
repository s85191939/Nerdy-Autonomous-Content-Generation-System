"""Improvement strategies: map weak dimension to Meta-calibrated regeneration instructions."""

IMPROVEMENT_STRATEGIES = {
    "clarity": (
        "Make the message understandable in under 3 seconds. "
        "The first line of primary_text MUST hook in ≤125 characters (before '...See More'). "
        "Use one clear takeaway, short sentences, 8th-grade reading level."
    ),
    "value_proposition": (
        "Strengthen the benefit with a specific, measurable outcome (e.g. '200+ point score increase'). "
        "The headline must be 5–8 words, benefit-driven not feature-driven. "
        "Replace generic claims with concrete proof."
    ),
    "cta": (
        "Make the call-to-action specific, low-friction, and funnel-matched. "
        "Use 'Learn More' for awareness, 'Sign Up'/'Get Started' for consideration, "
        "'Shop Now'/'Book Now' for conversion. The primary text should naturally build toward the CTA."
    ),
    "brand_voice": (
        "Align with Varsity Tutors: empowering, knowledgeable, approachable, results-focused. "
        "Lead with outcomes, not features. Confident but not arrogant."
    ),
    "emotional_resonance": (
        "Add a proven emotional hook: question, stat, story, bold claim, pain point, or curiosity gap. "
        "Tap into real motivation: parent worry, student ambition, test anxiety. "
        "Embed social proof (numbers, testimonials) to strengthen the emotional connection."
    ),
}


def get_improvement_hint(weak_dimension: str, brief: dict = None) -> str:
    """Return improvement hint — dynamic for custom briefs, default for Varsity Tutors."""
    if brief and brief.get("brand_name"):
        if weak_dimension == "brand_voice":
            brand_name = brief["brand_name"]
            tone = brief.get("tone", "professional, engaging")
            return f"Align with {brand_name}: {tone}."
        if weak_dimension == "emotional_resonance":
            audience = brief.get("audience", "target audience")
            return (
                f"Add a proven emotional hook that resonates with {audience}: "
                "question, stat, story, bold claim, pain point, or curiosity gap. "
                "Embed social proof to strengthen the connection."
            )
        if weak_dimension == "value_proposition":
            product = brief.get("product", "product")
            return (
                f"Strengthen the benefit with a specific, measurable outcome for {product}. "
                "Headline must be 5–8 words, benefit-driven."
            )
        if weak_dimension == "cta":
            return (
                "Make the CTA specific, low-friction, and funnel-matched. "
                "Use 'Learn More' for awareness, 'Sign Up'/'Get Started' for consideration, "
                "'Shop Now'/'Book Now' for conversion."
            )
        if weak_dimension == "clarity":
            return (
                "First line of primary_text must hook in ≤125 characters. "
                "One clear takeaway, short sentences, 8th-grade reading level."
            )
    return IMPROVEMENT_STRATEGIES.get(
        weak_dimension,
        f"Improve the dimension: {weak_dimension}.",
    )
