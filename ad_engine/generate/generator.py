"""Ad copy generator using Gemini from structured briefs."""

import json
import os
import re
from typing import Optional

from dotenv import load_dotenv

from ad_engine.generate.prompt_templates import (
    AD_GENERATION_SYSTEM,
    AD_GENERATION_USER,
    IMPROVEMENT_USER,
)
from ad_engine.utils import with_retry

load_dotenv()


def _get_client():
    try:
        import google.generativeai as genai
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY")
        genai.configure(api_key=key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except ImportError:
        raise ImportError("Install google-generativeai: pip install google-generativeai")


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

    def __init__(self, model=None, seed: Optional[int] = None):
        self._model = model or _get_client()
        self._seed = seed
        # GenerationConfig does not support random_seed in current Gemini SDK; seed still used for brief order in CLI
        self._generation_config = None

    def generate(self, brief: dict) -> dict:
        """Generate one ad from a brief. Brief keys: audience, product, goal, tone."""
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
        text = response.text if hasattr(response, "text") else str(response)
        return _parse_json_from_response(text)

    def improve(
        self,
        ad: dict,
        weak_dimension: str,
        rationale: str,
    ) -> dict:
        """Regenerate ad with targeted improvement for weak_dimension."""
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
        text = response.text if hasattr(response, "text") else str(response)
        return _parse_json_from_response(text)
