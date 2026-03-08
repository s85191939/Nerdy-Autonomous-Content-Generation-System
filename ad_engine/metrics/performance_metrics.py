"""Performance per token and quality trend metrics."""

from typing import Any, List, Optional


class PerformanceMetrics:
    """Track quality and cost across runs."""

    def __init__(self):
        self.runs: list[dict[str, Any]] = []

    def record_run(
        self,
        cycle: int,
        avg_score: float,
        token_cost: float,
        num_ads: int,
    ) -> None:
        metric = token_cost and (avg_score / token_cost) or 0.0
        self.runs.append({
            "cycle": cycle,
            "avg_score": avg_score,
            "token_cost": token_cost,
            "num_ads": num_ads,
            "performance_per_token": round(metric, 4),
        })

    def performance_per_token(self, cycle: Optional[int] = None) -> float:
        if not self.runs:
            return 0.0
        if cycle is not None:
            for r in self.runs:
                if r["cycle"] == cycle:
                    return r["performance_per_token"]
            return 0.0
        return self.runs[-1]["performance_per_token"]

    def quality_trend(self) -> List[float]:
        return [r["avg_score"] for r in self.runs]
