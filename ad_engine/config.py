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
