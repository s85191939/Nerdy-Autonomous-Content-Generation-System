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


class AdGenerator:
    """Generate FB/IG ad copy from briefs using Gemini."""

    def __init__(self, model=None, seed: Optional[int] = None, token_tracker=None):
        self._model = model or _get_client()
        self._seed = seed
        self._token_tracker = token_tracker
        # GenerationConfig does not support random_seed in current Gemini SDK; seed still used for brief order in CLI
        self._generation_config = None

    def generate(self, brief: dict) -> dict:
        """Generate one ad from a brief. Brief keys: audience, product, goal, tone."""
        try:
            return self._generate_impl(brief)
        except Exception as e:
            logger.warning("Ad generation failed, using fallback ad: %s", e)
            return dict(FALLBACK_AD)

    def _generate_impl(self, brief: dict) -> dict:
        """Internal generate; may raise."""
        user = AD_GENERATION_USER.format(
            audience=brief.get("audience", "Parents of high school students"),
            product=brief.get("product", "SAT tutoring program"),
            goal=brief.get("goal", "conversion"),
            tone=brief.get("tone", "reassuring, results-focused"),
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
        # Ensure required keys exist
        for key in ("primary_text", "headline", "description", "cta"):
            if key not in parsed or parsed[key] is None:
                parsed[key] = FALLBACK_AD.get(key, "")
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
        return parsed
