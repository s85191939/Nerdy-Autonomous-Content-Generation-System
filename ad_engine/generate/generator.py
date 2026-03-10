"""Ad copy generator using Gemini or OpenRouter from structured briefs."""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv

from ad_engine.config import FALLBACK_AD
from ad_engine.generate.prompt_templates import (
    AD_GENERATION_SYSTEM,
    AD_GENERATION_USER,
    IMPROVEMENT_USER,
    REFERENCE_PATTERNS_SNIPPET,
    VARIANT_ANGLES,
)
from ad_engine.llm import get_llm
from ad_engine.metrics.token_tracker import usage_from_response
from ad_engine.utils import with_retry

load_dotenv()
logger = logging.getLogger(__name__)


def _get_client():
    return get_llm()


def _parse_json_from_response(text: str) -> dict:
    """Extract a single JSON object from model output."""
    text = text.strip()
    # Try to find {...}
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _enforce_primary_text_length(ad: dict, max_visible: int = 125) -> None:
    """Ensure primary text visible portion is at most max_visible chars (Meta spec)."""
    pt = (ad.get("primary_text") or "").strip()
    if not pt or len(pt) <= max_visible:
        return
    ad["primary_text"] = pt[: max_visible - 3].rstrip() + "..."


class AdGenerator:
    """Generate FB/IG ad copy from briefs using Gemini."""

    def __init__(self, model=None, seed: Optional[int] = None, token_tracker=None):
        self._model = model or _get_client()
        self._seed = seed
        self._token_tracker = token_tracker
        # GenerationConfig does not support random_seed in current Gemini SDK; seed still used for brief order in CLI
        self._generation_config = None

    def generate(self, brief: dict, reference_insights: dict = None, creative_angle: str = None) -> dict:
        """Generate one ad from a brief. Optional reference_insights, optional creative_angle for A/B variants."""
        try:
            return self._generate_impl(brief, reference_insights, creative_angle)
        except Exception as e:
            logger.warning("Ad generation failed, using fallback ad: %s", e)
            return dict(FALLBACK_AD)

    def _generate_impl(self, brief: dict, reference_insights: dict = None, creative_angle: str = None) -> dict:
        system = AD_GENERATION_SYSTEM
        insights = reference_insights if reference_insights is not None else getattr(self, "_reference_insights", None)
        if insights and isinstance(insights, dict):
            hooks = insights.get("hooks") or []
            ctas = insights.get("ctas") or []
            angles = insights.get("tone_angles") or []
            if hooks or ctas or angles:
                snippet = REFERENCE_PATTERNS_SNIPPET.format(hooks=", ".join(hooks[:5]) or "N/A", ctas=", ".join(ctas[:5]) or "N/A", tone_angles=", ".join(angles[:4]) or "N/A")
                system = AD_GENERATION_SYSTEM + snippet
        creative_angle_suffix = ("\nCreative approach for this variant: " + creative_angle) if creative_angle else ""
        user = AD_GENERATION_USER.format(
            audience=brief.get("audience", "Parents of high school students"),
            product=brief.get("product", "SAT tutoring program"),
            goal=brief.get("goal", "conversion"),
            tone=brief.get("tone", "reassuring, results-focused"),
            creative_angle_suffix=creative_angle_suffix,
        )

        def _call():
            return self._model.generate_content(
                [system, user],
                generation_config=self._generation_config,
            )

        response = with_retry(_call)
        if self._token_tracker:
            self._token_tracker.add_from_usage(usage_from_response(response))
        text = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_json_from_response(text)
        # Ensure required keys exist
        for key in ("primary_text", "headline", "description", "cta"):
            if key not in parsed or parsed[key] is None:
                parsed[key] = FALLBACK_AD.get(key, "")
        _enforce_primary_text_length(parsed)
        return parsed

    def improve(
        self,
        ad: dict,
        weak_dimension: str,
        rationale: str,
    ) -> dict:
        """Regenerate ad with targeted improvement for weak_dimension."""
        try:
            return self._improve_impl(ad, weak_dimension, rationale)
        except Exception as e:
            logger.warning("Ad improvement failed, returning original ad: %s", e)
            return dict(ad) if ad else dict(FALLBACK_AD)

    def _improve_impl(
        self,
        ad: dict,
        weak_dimension: str,
        rationale: str,
    ) -> dict:
        """Internal improve; may raise."""
        user = IMPROVEMENT_USER.format(
            ad_json=json.dumps(ad, indent=2),
            weak_dimension=weak_dimension.replace("_", " ").title(),
            rationale=rationale,
        )

        def _call():
            return self._model.generate_content(
                [AD_GENERATION_SYSTEM, user],
                generation_config=self._generation_config,
            )

        response = with_retry(_call)
        if self._token_tracker:
            self._token_tracker.add_from_usage(usage_from_response(response))
        text = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_json_from_response(text)
        for key in ("primary_text", "headline", "description", "cta"):
            if key not in parsed or parsed[key] is None:
                parsed[key] = (ad or FALLBACK_AD).get(key, "")
        _enforce_primary_text_length(parsed)
        return parsed
