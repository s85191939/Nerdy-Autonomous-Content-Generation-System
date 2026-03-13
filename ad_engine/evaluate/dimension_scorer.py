"""LLM-as-judge: score ad on five dimensions with rationales."""

import json
import logging
import os
import re
from typing import List, Optional

from dotenv import load_dotenv

from ad_engine.config import DIMENSION_NAMES
from ad_engine.evaluate.aggregator import aggregate_scores
from ad_engine.llm import get_llm
from ad_engine.metrics.token_tracker import usage_from_response
from ad_engine.utils import with_retry

load_dotenv()
logger = logging.getLogger(__name__)

EVALUATION_SYSTEM = """You are an expert ad quality evaluator specializing in Facebook/Instagram (Meta) ads.

Evaluate each ad against the exact Meta ad copy structure. Score on a scale of 1-10 for these dimensions:

1. clarity — Is the message understandable in under 3 seconds?
   - First line of primary_text must hook in ≤125 characters (visible before "...See More").
   - One clear takeaway, no jargon, 8th-grade reading level.
   (1=confusing/long-winded, 10=crystal clear hook + scannable body)

2. value_proposition — Does it communicate a specific, compelling benefit?
   - Must include a measurable or concrete outcome, not generic claims.
   - Headline should be 5–8 words, benefit-driven (not feature-driven).
   (1=generic "we're the best", 10=specific e.g. "raise SAT 200+ points")

3. cta — Is the call-to-action clear, compelling, and funnel-appropriate?
   - CTA button must match funnel stage: "Learn More" (awareness), "Sign Up"/"Get Started" (consideration), "Shop Now"/"Book Now" (conversion).
   - The primary text should naturally lead to the CTA — not just slap it on.
   (1=missing/vague CTA, 10=specific, low-friction, funnel-matched)

4. brand_voice — Does it sound like Varsity Tutors: empowering, knowledgeable, approachable, results-focused?
   - Confident but not arrogant. Expert but not elitist.
   - Leads with outcomes, not features.
   (1=generic/off-brand, 10=distinctly on-brand)

5. emotional_resonance — Does it connect emotionally with the target audience?
   - Uses proven hook types: question, stat, story, bold claim, pain point, or curiosity gap.
   - Taps into real motivation (parent worry, student ambition, test anxiety).
   - Social proof (numbers, testimonials, results) strengthens emotional impact.
   (1=flat/forgettable, 10=scroll-stopping emotional connection)

## Meta Structure Penalties:
- If first line of primary_text exceeds 125 characters → cap clarity at 6.
- If headline exceeds 8 words → cap value_proposition at 6.
- If CTA doesn't match the stated goal/funnel stage → cap cta at 5.

For each dimension also give a confidence score 1-10: how certain you are about your score (10=very certain, 1=guessing). Use confidence to signal when the ad is ambiguous or you're uncertain.

Respond with ONLY a single JSON object. No markdown. Keys: clarity, value_proposition, cta, brand_voice, emotional_resonance. Each value is an object: {"score": <1-10>, "rationale": "<short reason>", "confidence": <1-10>}.
Example: {"clarity": {"score": 8, "rationale": "Strong question hook in 95 chars. Scannable body.", "confidence": 9}, ...}"""


def build_evaluation_system(brief: dict = None) -> str:
    """Return evaluation system prompt — dynamic for custom briefs, default for Varsity Tutors."""
    if brief is None or not brief.get("brand_name"):
        return EVALUATION_SYSTEM
    brand_name = brief.get("brand_name", "Brand")
    tone = brief.get("tone", "professional, engaging")
    product = brief.get("product", "product")
    audience = brief.get("audience", "target audience")
    return f"""You are an expert ad quality evaluator specializing in Facebook/Instagram (Meta) ads.

Evaluate each ad against the exact Meta ad copy structure. Score on a scale of 1-10 for these dimensions:

1. clarity — Is the message understandable in under 3 seconds?
   - First line of primary_text must hook in ≤125 characters (visible before "...See More").
   - One clear takeaway, no jargon, 8th-grade reading level.
   (1=confusing/long-winded, 10=crystal clear hook + scannable body)

2. value_proposition — Does it communicate a specific, compelling benefit for {product}?
   - Must include a measurable or concrete outcome, not generic claims.
   - Headline should be 5–8 words, benefit-driven (not feature-driven).
   (1=generic, 10=specific and compelling)

3. cta — Is the call-to-action clear, compelling, and funnel-appropriate?
   - CTA button must match funnel stage: "Learn More" (awareness), "Sign Up"/"Get Started" (consideration), "Shop Now"/"Book Now" (conversion).
   - The primary text should naturally lead to the CTA.
   (1=missing/vague CTA, 10=specific, low-friction, funnel-matched)

4. brand_voice — Does it sound like {brand_name}: {tone}?
   - Leads with outcomes, not features.
   (1=generic/off-brand, 10=distinctly on-brand)

5. emotional_resonance — Does it connect emotionally with {audience}?
   - Uses proven hook types: question, stat, story, bold claim, pain point, or curiosity gap.
   - Taps into real motivation and social proof.
   (1=flat/forgettable, 10=scroll-stopping emotional connection)

## Meta Structure Penalties:
- If first line of primary_text exceeds 125 characters → cap clarity at 6.
- If headline exceeds 8 words → cap value_proposition at 6.
- If CTA doesn't match the stated goal/funnel stage → cap cta at 5.

For each dimension also give a confidence score 1-10: how certain you are about your score (10=very certain, 1=guessing). Use confidence to signal when the ad is ambiguous or you're uncertain.

Respond with ONLY a single JSON object. No markdown. Keys: clarity, value_proposition, cta, brand_voice, emotional_resonance. Each value is an object: {{"score": <1-10>, "rationale": "<short reason>", "confidence": <1-10>}}.
Example: {{"clarity": {{"score": 8, "rationale": "Strong question hook in 95 chars.", "confidence": 9}}, ...}}"""

EVALUATION_USER = """Ad to evaluate (JSON):
{ad_json}

Return one JSON object with keys clarity, value_proposition, cta, brand_voice, emotional_resonance. Each value: {{"score": 1-10, "rationale": "...", "confidence": 1-10}}."""


def _get_model():
    return get_llm()


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_evaluation(text: str) -> dict:
    text = _strip_markdown_fences(text)
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


def default_evaluation(overall_score: float = 5.0, dimension_weights: Optional[dict] = None) -> dict:
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
        "overall_score": round(aggregate_scores(scores_only, dimension_weights), 2),
        "confidence": 5.0,
    }


class Evaluator:
    """Score ads on five dimensions using LLM-as-judge."""

    def __init__(self, model=None, seed: Optional[int] = None, token_tracker=None, dimension_weights: Optional[dict] = None):
        self._model = model or _get_model()
        self._seed = seed
        self._token_tracker = token_tracker
        self._dimension_weights = dimension_weights
        # GenerationConfig does not support random_seed in current Gemini SDK
        self._config = None

    def evaluate(self, ad: dict, brief: dict = None) -> dict:
        """Return dimension scores with rationales, overall_score, and confidence.
        Tries once, falls back to default_evaluation on failure (fail-fast)."""
        try:
            return self._evaluate_impl(ad, brief=brief)
        except Exception as e:
            logger.warning("Evaluation failed: %s — using default score", e)
            return default_evaluation(5.0, self._dimension_weights)

    def evaluate_batch(self, ads: List[dict], brief: dict = None) -> List[dict]:
        """Evaluate multiple ads in parallel using ThreadPoolExecutor.
        Each ad uses the proven single-ad evaluator. Fast because all N calls run concurrently."""
        if not ads:
            return []
        if len(ads) == 1:
            return [self.evaluate(ads[0], brief=brief)]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(ads), 8)) as executor:
            futures = [executor.submit(self.evaluate, ad, brief) for ad in ads]
            return [f.result() for f in futures]

    def _evaluate_impl(self, ad: dict, brief: dict = None) -> dict:
        """Internal evaluate; may raise."""
        evaluation_system = build_evaluation_system(brief)
        ad_json = json.dumps(ad, indent=2)
        user = EVALUATION_USER.format(ad_json=ad_json)

        def _call():
            return self._model.generate_content(
                [evaluation_system, user],
                generation_config=self._config,
            )

        response = with_retry(_call, max_retries=1)
        if self._token_tracker:
            self._token_tracker.add_from_usage(usage_from_response(response))
        text = response.text if hasattr(response, "text") else str(response)
        dim_results = _parse_evaluation(text)
        scores_only = {d: dim_results[d]["score"] for d in DIMENSION_NAMES}
        overall = aggregate_scores(scores_only, self._dimension_weights)
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
