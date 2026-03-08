"""Evaluation: dimension scoring, aggregation, LLM-as-judge."""

from ad_engine.evaluate.evaluator import Evaluator
from ad_engine.evaluate.aggregator import aggregate_scores
from ad_engine.config import DIMENSION_WEIGHTS

__all__ = ["Evaluator", "aggregate_scores", "DIMENSION_WEIGHTS"]
