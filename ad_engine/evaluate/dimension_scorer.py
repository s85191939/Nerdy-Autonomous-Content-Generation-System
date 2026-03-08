"""LLM-as-judge: score ad on five dimensions with rationales."""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv

from ad_engine.config import DIMENSION_NAMES
from ad_engine.evaluate.aggregator import aggregate_scores
from ad_engine.llm import get_llm
from ad_engine.metrics.token_tracker import usage_from_response
from ad_engine.utils import with_retry

load_dotenv()
logger = logging.getLogger(__name__)

EVALUATION_SYSTEM = """You are an expert ad quality evaluator for Facebook/Instagram ads. Score each ad on a scale of 1-10 for these dimensions:

1. clarity — Is the message understandable in under 3 seconds? (1=confusing, 10=crystal clear)
2. value_proposition — Does it communicate a specific, compelling benefit? (1=generic, 10=specific e.g. "raise SAT 200+ points")
3. cta — Is the next step clear and compelling? (1=no/vague CTA, 10=specific, low-friction)
4. brand_voice — Does it sound like Varsity Tutors: empowering, knowledgeable, approachable? (1=generic, 10=distinctly on-brand)
5. emotional_resonance — Does it connect emotionally? (1=flat, 10=taps into real motivation e.g. parent worry, test anxiety)

For each dimension also give a confidence score 1-10: how certain you are about your score (10=very certain, 1=guessing). Use confidence to signal when the ad is ambiguous or you're uncertain.

Respond with ONLY a single JSON object. No markdown. Keys: clarity, value_proposition, cta, brand_voice, emotional_resonance. Each value is an object: {"score": <1-10>, "rationale": "<short reason>", "confidence": <1-10>}.
Example: {"clarity": {"score": 8, "rationale": "Clear hook.", "confidence": 9}, ...}"""

EVALUATION_USER = """Ad to evaluate (JSON):
{ad_json}

Return one JSON object with keys clarity, value_proposition, cta, brand_voice, emotional_resonance. Each value: {{"score": 1-10, "rationale": "...", "confidence": 1-10}}."""


def _get_model():
    return get_llm()


def _parse_evaluation(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        raw = json.loads(match.group())
        out = {}
        for dim in DIMENSION_NAMES:
            v = raw.get(dim)
            if isinstance(v, dict):
                out[dim] = {
                    "score": int(v.get("score", 0)),
                    "rationale": v.get("rationale", ""),
                    "confidence": int(v.get("confidence", 5)),
                }
            elif isinstance(v, (int, float)):
                out[dim] = {"score": int(v), "rationale": "", "confidence": 5}
            else:
                out[dim] = {"score": 0, "rationale": "", "confidence": 0}
        return out
    raise ValueError("No JSON found in evaluation response")


def default_evaluation(overall_score: float = 5.0) -> dict:
    """Return a valid evaluation dict when LLM evaluation fails. Never raises."""
    score_per_dim = max(1, min(10, int(round(overall_score))))
    dimensions = {}
    for dim in DIMENSION_NAMES:
        dimensions[dim] = {
            "score": score_per_dim,
            "rationale": "Evaluation unavailable; default score applied.",
            "confidence": 5,
        }
    scores_only = {d: dimensions[d]["score"] for d in DIMENSION_NAMES}
    return {
        "dimensions": dimensions,
        "scores": scores_only,
        "overall_score": round(aggregate_scores(scores_only), 2),
        "confidence": 5.0,
    }


class Evaluator:
    """Score ads on five dimensions using LLM-as-judge."""

    def __init__(self, model=None, seed: Optional[int] = None, token_tracker=None):
        self._model = model or _get_model()
        self._seed = seed
        self._token_tracker = token_tracker
        # GenerationConfig does not support random_seed in current Gemini SDK
        self._config = None

    def evaluate(self, ad: dict) -> dict:
        """Return dimension scores with rationales, overall_score, and confidence. On failure returns default_evaluation."""
        try:
            return self._evaluate_impl(ad)
        except Exception as e:
            logger.warning("Evaluation failed, using default evaluation: %s", e)
            return default_evaluation(5.0)

    def _evaluate_impl(self, ad: dict) -> dict:
        """Internal evaluate; may raise."""
        ad_json = json.dumps(ad, indent=2)
        user = EVALUATION_USER.format(ad_json=ad_json)

        def _call():
            return self._model.generate_content(
                [EVALUATION_SYSTEM, user],
                generation_config=self._config,
            )

        response = with_retry(_call)
        if self._token_tracker:
            self._token_tracker.add_from_usage(usage_from_response(response))
        text = response.text if hasattr(response, "text") else str(response)
        dim_results = _parse_evaluation(text)
        scores_only = {d: dim_results[d]["score"] for d in DIMENSION_NAMES}
        overall = aggregate_scores(scores_only)
        return {
            "dimensions": dim_results,
            "scores": scores_only,
            "overall_score": round(overall, 2),
            "confidence": _aggregate_confidence(dim_results),
        }


def _aggregate_confidence(dim_results: dict) -> float:
    """Average confidence across dimensions (1-10)."""
    confs = [dim_results[d].get("confidence", 5) for d in DIMENSION_NAMES]
    return round(sum(confs) / len(confs), 2) if confs else 5.0
