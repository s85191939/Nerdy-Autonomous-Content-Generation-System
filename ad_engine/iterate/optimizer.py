"""Iteration engine: generate → evaluate → improve until threshold or max iterations."""

from typing import Any

from ad_engine.config import DIMENSION_NAMES, QUALITY_THRESHOLD
from ad_engine.evaluate import Evaluator, aggregate_scores
from ad_engine.generate import AdGenerator
from ad_engine.iterate.improvement_strategies import get_improvement_hint


def _weakest_dimension(scores: dict) -> str:
    """Return dimension with lowest score."""
    return min(DIMENSION_NAMES, key=lambda d: scores.get(d, 10.0))


class IterationEngine:
    """Runs the feedback loop: generate, evaluate, optionally regenerate."""

    def __init__(
        self,
        generator: AdGenerator,
        evaluator: Evaluator,
        quality_threshold: float = QUALITY_THRESHOLD,
        max_iterations: int = 5,
    ):
        self.generator = generator
        self.evaluator = evaluator
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations

    def run_for_brief(
        self,
        brief: dict,
    ) -> dict:
        """
        Generate ad for brief, evaluate, and iterate until score >= threshold or max_iterations.
        Returns dict with ad, evaluation, iteration_count, accepted.
        """
        ad = self.generator.generate(brief)
        evaluation = self.evaluator.evaluate(ad)
        iteration_count = 1
        history = [{"iteration": 1, "ad": ad, "evaluation": evaluation}]

        while evaluation["overall_score"] < self.quality_threshold and iteration_count < self.max_iterations:
            weak = _weakest_dimension(evaluation["scores"])
            rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak)
            ad = self.generator.improve(ad, weak, rationale)
            evaluation = self.evaluator.evaluate(ad)
            iteration_count += 1
            history.append({"iteration": iteration_count, "ad": ad, "evaluation": evaluation})

        accepted = evaluation["overall_score"] >= self.quality_threshold
        return {
            "brief": brief,
            "ad": ad,
            "evaluation": evaluation,
            "iteration_count": iteration_count,
            "accepted": accepted,
            "history": history,
        }
