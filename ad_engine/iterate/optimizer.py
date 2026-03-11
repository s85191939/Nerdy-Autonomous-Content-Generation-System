"""Iteration engine: generate → evaluate → improve until threshold or max iterations."""

import logging
from typing import Any

from ad_engine.config import DIMENSION_NAMES, FALLBACK_AD, QUALITY_THRESHOLD
from ad_engine.evaluate import Evaluator, aggregate_scores
from ad_engine.evaluate.dimension_scorer import default_evaluation
from ad_engine.generate import AdGenerator
from ad_engine.iterate.improvement_strategies import get_improvement_hint

logger = logging.getLogger(__name__)


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
        creative_angle: str = None,
    ) -> dict:
        """
        Generate ad for brief, evaluate, and iterate until score >= threshold or max_iterations.
        Returns dict with ad, evaluation, iteration_count, accepted. Never raises; on failure returns fallback result.
        """
        try:
            return self._run_for_brief_impl(brief, creative_angle)
        except Exception as e:
            logger.warning("run_for_brief failed for brief, returning fallback result: %s", e)
            fallback_eval = default_evaluation(5.0)
            return {
                "brief": brief,
                "ad": dict(FALLBACK_AD),
                "evaluation": fallback_eval,
                "iteration_count": 0,
                "accepted": False,
                "history": [
                    {"iteration": 1, "ad": FALLBACK_AD, "evaluation": fallback_eval},
                ],
            }

    def _run_for_brief_impl(self, brief: dict, creative_angle: str = None) -> dict:
        """Internal run; may raise."""
        ad = self.generator.generate(brief, creative_angle=creative_angle)
        evaluation = self.evaluator.evaluate(ad, brief=brief)
        iteration_count = 1
        history = [{"iteration": 1, "ad": ad, "evaluation": evaluation}]

        while evaluation["overall_score"] < self.quality_threshold and iteration_count < self.max_iterations:
            weak = _weakest_dimension(evaluation["scores"])
            rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak, brief=brief)
            ad = self.generator.improve(ad, weak, rationale, brief=brief)
            evaluation = self.evaluator.evaluate(ad, brief=brief)
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

    def run_from_ad(self, ad: dict, brief: dict) -> dict:
        """Re-evaluate and iterate on an existing ad. Use to run another improvement round on a campaign ad."""
        try:
            return self._run_from_ad_impl(ad, brief)
        except Exception as e:
            logger.warning("run_from_ad failed: %s", e)
            fallback_eval = default_evaluation(5.0)
            return {
                "brief": brief,
                "ad": dict(ad) if ad else dict(FALLBACK_AD),
                "evaluation": fallback_eval,
                "iteration_count": 0,
                "accepted": False,
                "history": [{"iteration": 1, "ad": ad or FALLBACK_AD, "evaluation": fallback_eval}],
            }

    def run_one_improvement(self, ad: dict, brief: dict) -> dict:
        """Run exactly one improve step on an existing ad (for UI 'Make it better' button). Returns result with updated ad and history."""
        evaluation = self.evaluator.evaluate(ad, brief=brief)
        weak = _weakest_dimension(evaluation["scores"])
        rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak, brief=brief)
        new_ad = self.generator.improve(dict(ad), weak, rationale, brief=brief)
        new_eval = self.evaluator.evaluate(new_ad, brief=brief)
        return {
            "brief": brief,
            "ad": new_ad,
            "evaluation": new_eval,
            "iteration_count": 2,  # original + 1 improve
            "accepted": new_eval["overall_score"] >= self.quality_threshold,
            "history": [
                {"iteration": 1, "ad": dict(ad), "evaluation": evaluation},
                {"iteration": 2, "ad": dict(new_ad), "evaluation": new_eval},
            ],
        }

    def _run_from_ad_impl(self, ad: dict, brief: dict) -> dict:
        evaluation = self.evaluator.evaluate(ad, brief=brief)
        iteration_count = 1
        history = [{"iteration": 1, "ad": dict(ad), "evaluation": evaluation}]
        current_ad = dict(ad)
        while evaluation["overall_score"] < self.quality_threshold and iteration_count < self.max_iterations:
            weak = _weakest_dimension(evaluation["scores"])
            rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak, brief=brief)
            current_ad = self.generator.improve(current_ad, weak, rationale, brief=brief)
            evaluation = self.evaluator.evaluate(current_ad, brief=brief)
            iteration_count += 1
            history.append({"iteration": iteration_count, "ad": dict(current_ad), "evaluation": evaluation})
        accepted = evaluation["overall_score"] >= self.quality_threshold
        return {
            "brief": brief,
            "ad": current_ad,
            "evaluation": evaluation,
            "iteration_count": iteration_count,
            "accepted": accepted,
            "history": history,
        }
