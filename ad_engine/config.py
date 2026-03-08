"""Configuration constants and defaults."""

QUALITY_THRESHOLD = 7.0
# Allow 5+ iteration cycles per ad (rubric: "5+ iteration cycles with clear methodology")
MAX_ITERATIONS = 6

# Dimension weights for aggregate score (sum = 1.0)
DIMENSION_WEIGHTS = {
    "clarity": 0.25,
    "value_proposition": 0.25,
    "emotional_resonance": 0.20,
    "cta": 0.15,
    "brand_voice": 0.15,
}

DIMENSION_NAMES = [
    "clarity",
    "value_proposition",
    "cta",
    "brand_voice",
    "emotional_resonance",
]

# Fallback ad when generation fails (ensures pipeline never returns "no result")
FALLBACK_AD = {
    "primary_text": "We're here to help your student reach their goals. Get expert support today.",
    "headline": "Expert Tutoring Support",
    "description": "Quality tutoring when you need it.",
    "cta": "Learn More",
}
