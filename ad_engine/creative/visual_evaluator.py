"""Visual evaluation for ad creatives (v2): brand consistency and engagement potential.

Scores generated creative (image concept + ad copy) when an image is produced.
Uses text-based LLM scoring when no vision API is available.
Never raises; returns None or default scores on failure.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from ad_engine.llm import get_llm
from ad_engine.metrics.token_tracker import usage_from_response
from ad_engine.utils import with_retry

logger = logging.getLogger(__name__)

VISUAL_EVAL_SYSTEM = """You are an expert at judging Facebook/Instagram ad creative fit.
Score the described creative (image concept + ad copy) on two dimensions, 1-10:
1. brand_consistency — Does this creative fit Varsity Tutors (Nerdy): empowering, knowledgeable, approachable, results-focused? (1=generic/off-brand, 10=distinctly on-brand)
2. engagement_potential — Would this stop the scroll and invite engagement? (1=forgettable, 10=highly engaging)

Respond with ONLY a JSON object: {"brand_consistency": <1-10>, "engagement_potential": <1-10>}."""

VISUAL_EVAL_USER = """Ad copy (primary text, headline, etc.):
{ad_json}

Image concept: {image_concept}

Rate brand_consistency and engagement_potential 1-10. Return only the JSON object."""


def _build_image_concept(brief: dict, ad_copy: dict) -> str:
    """Short description of the image concept for evaluation."""
    product = brief.get("product", "product")
    audience = brief.get("audience", "audience")
    headline = (ad_copy.get("headline") or ad_copy.get("primary_text") or "")[:80]
    return f"Professional ad image for {product}, targeting {audience}. Concept: {headline}"


def evaluate_visual(
    brief: dict,
    ad_copy: dict,
    image_path: Optional[Path] = None,
    token_tracker=None,
) -> Optional[Dict[str, int]]:
    """
    Score creative for brand consistency and engagement potential (1-10 each).
    Uses text-based evaluation (image concept + ad copy). Returns None on failure.
    """
    try:
        model = get_llm()
        image_concept = _build_image_concept(brief, ad_copy)
        ad_json = json.dumps(
            {k: ad_copy.get(k) for k in ("primary_text", "headline", "description", "cta") if ad_copy.get(k)},
            indent=2,
        )
        user = VISUAL_EVAL_USER.format(ad_json=ad_json, image_concept=image_concept)

        def _call():
            return model.generate_content([VISUAL_EVAL_SYSTEM, user])

        response = with_retry(_call)
        if token_tracker and hasattr(response, "usage_metadata"):
            try:
                token_tracker.add_from_usage(usage_from_response(response))
            except Exception:
                pass
        text = response.text if hasattr(response, "text") else str(response)
        # Parse JSON with optional whitespace
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
        if match:
            raw = json.loads(match.group())
            bc = raw.get("brand_consistency", 5)
            ep = raw.get("engagement_potential", 5)
            return {
                "brand_consistency": max(1, min(10, int(bc) if isinstance(bc, (int, float)) else 5)),
                "engagement_potential": max(1, min(10, int(ep) if isinstance(ep, (int, float)) else 5)),
            }
    except Exception as e:
        logger.debug("Visual evaluation failed: %s", e)
    return None
