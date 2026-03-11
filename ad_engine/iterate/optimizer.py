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
        best_ad = dict(ad)
        best_eval = evaluation

        while evaluation["overall_score"] < self.quality_threshold and iteration_count < self.max_iterations:
            prev_score = evaluation["overall_score"]
            weak = _weakest_dimension(evaluation["scores"])
            rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak, brief=brief)
            new_ad = self.generator.improve(ad, weak, rationale, brief=brief)
            new_eval = self.evaluator.evaluate(new_ad, brief=brief)
            iteration_count += 1
            history.append({"iteration": iteration_count, "ad": new_ad, "evaluation": new_eval})
            # Quality ratchet: only accept if score improved
            if new_eval["overall_score"] >= best_eval["overall_score"]:
                ad = new_ad
                evaluation = new_eval
                best_ad = dict(new_ad)
                best_eval = new_eval
            else:
                logger.debug("Iteration %d regressed (%.2f → %.2f), keeping best (%.2f)", iteration_count, prev_score, new_eval["overall_score"], best_eval["overall_score"])
                ad = dict(best_ad)
                evaluation = best_eval
            improvement = evaluation["overall_score"] - prev_score
            if improvement < 0.3 and iteration_count >= 3:
                logger.debug("Early stop at iteration %d: improvement %.2f < 0.3", iteration_count, improvement)
                break

        accepted = best_eval["overall_score"] >= self.quality_threshold
        return {
            "brief": brief,
            "ad": best_ad,
            "evaluation": best_eval,
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

    def run_one_improvement(self, ad: dict, brief: dict, min_score: float = 0.0) -> dict:
        """Run exactly one improve step on an existing ad (for UI 'Make it better' button).
        Quality ratchet: if the new version scores worse than BOTH the fresh re-eval
        AND the stored min_score floor, keeps the original with the floor score.
        min_score: the stored historical score that must never be undercut."""
        evaluation = self.evaluator.evaluate(ad, brief=brief)
        weak = _weakest_dimension(evaluation["scores"])
        rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak, brief=brief)
        new_ad = self.generator.improve(dict(ad), weak, rationale, brief=brief)
        new_eval = self.evaluator.evaluate(new_ad, brief=brief)

        # Pick the best of: new_eval, fresh re-eval, and the stored min_score floor
        best_score = max(new_eval["overall_score"], evaluation["overall_score"], min_score)
        if new_eval["overall_score"] >= best_score:
            use_ad = new_ad
            use_eval = new_eval
        elif evaluation["overall_score"] >= best_score:
            use_ad = dict(ad)
            use_eval = evaluation
        else:
            # Both fresh evals are below the stored floor — keep original ad, use floor score
            logger.info("Both fresh evals (%.2f, %.2f) below stored floor %.2f — keeping original",
                        evaluation["overall_score"], new_eval["overall_score"], min_score)
            use_ad = dict(ad)
            use_eval = evaluation  # will be overridden by caller with stored scores

        return {
            "brief": brief,
            "ad": use_ad,
            "evaluation": use_eval,
            "best_score": best_score,
            "iteration_count": 2,  # original + 1 improve
            "accepted": best_score >= self.quality_threshold,
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
        best_ad = dict(ad)
        best_eval = evaluation
        while evaluation["overall_score"] < self.quality_threshold and iteration_count < self.max_iterations:
            prev_score = evaluation["overall_score"]
            weak = _weakest_dimension(evaluation["scores"])
            rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak, brief=brief)
            new_ad = self.generator.improve(current_ad, weak, rationale, brief=brief)
            new_eval = self.evaluator.evaluate(new_ad, brief=brief)
            iteration_count += 1
            history.append({"iteration": iteration_count, "ad": dict(new_ad), "evaluation": new_eval})
            # Quality ratchet: only accept if score improved
            if new_eval["overall_score"] >= best_eval["overall_score"]:
                current_ad = new_ad
                evaluation = new_eval
                best_ad = dict(new_ad)
                best_eval = new_eval
            else:
                logger.debug("Iteration %d regressed (%.2f → %.2f), keeping best (%.2f)", iteration_count, prev_score, new_eval["overall_score"], best_eval["overall_score"])
                current_ad = dict(best_ad)
                evaluation = best_eval
            # Early stop: if score barely improved across cycles
            improvement = evaluation["overall_score"] - prev_score
            if improvement < 0.3 and iteration_count >= 3:
                logger.debug("Early stop at iteration %d: improvement %.2f < 0.3", iteration_count, improvement)
                break
        accepted = best_eval["overall_score"] >= self.quality_threshold
        return {
            "brief": brief,
            "ad": best_ad,
            "evaluation": best_eval,
            "iteration_count": iteration_count,
            "accepted": accepted,
            "history": history,
        }
