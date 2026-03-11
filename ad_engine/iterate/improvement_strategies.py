"""Improvement strategies: map weak dimension to regeneration instructions."""

IMPROVEMENT_STRATEGIES = {
    "clarity": "Make the message clearer and easier to grasp in under 3 seconds. Use a single clear takeaway.",
    "value_proposition": "Strengthen the benefit with a specific outcome (e.g. score improvement, time saved).",
    "cta": "Make the call-to-action more specific and low-friction (e.g. 'Start your free practice test').",
    "brand_voice": "Align with Varsity Tutors: empowering, knowledgeable, approachable, results-focused.",
    "emotional_resonance": "Add emotional hook: parent worry, student ambition, or test anxiety.",
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
            return f"Add emotional hook that resonates with {audience}."
        if weak_dimension == "value_proposition":
            product = brief.get("product", "product")
            return f"Strengthen the benefit with a specific outcome for {product}."
    return IMPROVEMENT_STRATEGIES.get(
        weak_dimension,
        f"Improve the dimension: {weak_dimension}.",
    )
