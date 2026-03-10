"""v3: Agentic orchestration — researcher, writer, editor, evaluator agents.

Spec: "Agentic orchestration (researcher, writer, editor, evaluator agents)."
These agents wrap existing components with clear roles; the pipeline can use
IterationEngine (single flow) or run_for_brief_agentic (explicit agents).
"""

from pathlib import Path
from typing import Any, Dict, Optional

from ad_engine.config import DIMENSION_NAMES, FALLBACK_AD, QUALITY_THRESHOLD
from ad_engine.evaluate import Evaluator, aggregate_scores
from ad_engine.evaluate.dimension_scorer import default_evaluation
from ad_engine.generate import AdGenerator
from ad_engine.iterate.improvement_strategies import get_improvement_hint


def _weakest_dimension(scores: dict) -> str:
    return min(DIMENSION_NAMES, key=lambda d: scores.get(d, 10.0))


class ResearcherAgent:
    """Gathers context: reference insights (competitor patterns, hooks, CTAs) for the brief."""

    def __init__(self, insights_path: Optional[Path] = None):
        self.insights_path = Path(insights_path) if insights_path else None
        self._insights = None

    def get_context(self, brief: dict) -> dict:
        """Return context (e.g. competitor insights) for this brief. Never raises."""
        if self._insights is not None:
            return self._insights
        if self.insights_path and self.insights_path.exists():
            try:
                from ad_engine.competitor.insights import load_insights
                self._insights = load_insights(self.insights_path)
                return self._insights
            except Exception:
                pass
        return {"hooks": [], "ctas": [], "tone_angles": []}


class WriterAgent:
    """Generates ad copy from brief and optional context (researcher output)."""

    def __init__(self, generator: AdGenerator):
        self.generator = generator

    def generate(self, brief: dict, context: Optional[dict] = None, creative_angle: Optional[str] = None) -> dict:
        """Produce one ad from brief; context (hooks, ctas) can enrich the generator."""
        if context and getattr(self.generator, "_reference_insights", None) is None:
            self.generator._reference_insights = context
        return self.generator.generate(brief, reference_insights=context, creative_angle=creative_angle)


class EditorAgent:
    """Improves ad copy by targeting the weakest dimension (targeted regeneration)."""

    def __init__(self, generator: AdGenerator):
        self.generator = generator

    def improve(self, ad: dict, weak_dimension: str, rationale: str) -> dict:
        """Return improved ad focusing on weak_dimension."""
        return self.generator.improve(ad, weak_dimension, rationale)


class EvaluatorAgent:
    """Scores ad on five dimensions with rationales and confidence."""

    def __init__(self, evaluator: Evaluator):
        self.evaluator = evaluator

    def evaluate(self, ad: dict) -> dict:
        """Return evaluation dict: scores, dimensions (rationale, confidence), overall_score, confidence."""
        return self.evaluator.evaluate(ad)


def run_for_brief_agentic(
    brief: dict,
    researcher: ResearcherAgent,
    writer: WriterAgent,
    editor: EditorAgent,
    evaluator_agent: EvaluatorAgent,
    quality_threshold: float = QUALITY_THRESHOLD,
    max_iterations: int = 5,
    creative_angle: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full agentic loop: Researcher → Writer → Evaluator → [Editor → Evaluator]* until threshold or max.
    Returns same shape as IterationEngine.run_for_brief: brief, ad, evaluation, iteration_count, accepted, history.
    """
    try:
        context = researcher.get_context(brief)
        ad = writer.generate(brief, context=context, creative_angle=creative_angle)
        evaluation = evaluator_agent.evaluate(ad)
        iteration_count = 1
        history = [{"iteration": 1, "ad": ad, "evaluation": evaluation}]

        while evaluation["overall_score"] < quality_threshold and iteration_count < max_iterations:
            weak = _weakest_dimension(evaluation["scores"])
            rationale = evaluation["dimensions"][weak].get("rationale", "") or get_improvement_hint(weak)
            ad = editor.improve(ad, weak, rationale)
            evaluation = evaluator_agent.evaluate(ad)
            iteration_count += 1
            history.append({"iteration": iteration_count, "ad": ad, "evaluation": evaluation})

        accepted = evaluation["overall_score"] >= quality_threshold
        return {
            "brief": brief,
            "ad": ad,
            "evaluation": evaluation,
            "iteration_count": iteration_count,
            "accepted": accepted,
            "history": history,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("run_for_brief_agentic failed: %s", e)
        fallback_eval = default_evaluation(5.0)
        return {
            "brief": brief,
            "ad": dict(FALLBACK_AD),
            "evaluation": fallback_eval,
            "iteration_count": 0,
            "accepted": False,
            "history": [{"iteration": 1, "ad": FALLBACK_AD, "evaluation": fallback_eval}],
        }
