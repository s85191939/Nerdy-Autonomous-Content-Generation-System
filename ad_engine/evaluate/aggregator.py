"""Score aggregation: weighted overall score from dimension scores."""

from typing import Optional

from ad_engine.config import DIMENSION_WEIGHTS


def aggregate_scores(scores: dict[str, float], weights: Optional[dict] = None) -> float:
    """Compute weighted average. Missing dimensions get 0 weight. Uses DIMENSION_WEIGHTS if weights is None."""
    w = weights if weights is not None else DIMENSION_WEIGHTS
    total = 0.0
    weight_sum = 0.0
    for dim, weight in w.items():
        if dim in scores and scores[dim] is not None:
            total += weight * float(scores[dim])
            weight_sum += weight
    if weight_sum <= 0:
        return 0.0
    return total / weight_sum
