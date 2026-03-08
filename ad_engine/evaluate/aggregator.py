"""Score aggregation: weighted overall score from dimension scores."""

from ad_engine.config import DIMENSION_WEIGHTS


def aggregate_scores(scores: dict[str, float]) -> float:
    """Compute weighted average. Missing dimensions get 0 weight."""
    total = 0.0
    weight_sum = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        if dim in scores and scores[dim] is not None:
            total += weight * float(scores[dim])
            weight_sum += weight
    if weight_sum <= 0:
        return 0.0
    return total / weight_sum
