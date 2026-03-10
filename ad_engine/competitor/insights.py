"""Extract patterns from competitor ads and rewrite as brand. Never raises; returns safe defaults on failure."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ad_engine.generate.prompt_templates import (
    COMPETITOR_PATTERNS_SYSTEM,
    COMPETITOR_PATTERNS_USER,
    REWRITE_AS_BRAND_SYSTEM,
    REWRITE_AS_BRAND_USER,
)
from ad_engine.llm import get_llm
from ad_engine.utils import with_retry

logger = logging.getLogger(__name__)

DEFAULT_INSIGHTS = {"hooks": [], "ctas": [], "tone_angles": []}


def _parse_json(text: str) -> Optional[Dict]:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def extract_patterns(ads: List[Dict], token_tracker=None) -> Dict[str, List[str]]:
    """Analyze competitor ads; return { hooks, ctas, tone_angles }. On failure return DEFAULT_INSIGHTS."""
    if not ads:
        return dict(DEFAULT_INSIGHTS)
    try:
        model = get_llm()
        ads_json = json.dumps(ads, indent=0)[:12000]
        user = COMPETITOR_PATTERNS_USER.format(ads_json=ads_json)
        response = with_retry(lambda: model.generate_content([COMPETITOR_PATTERNS_SYSTEM, user]))
        if token_tracker and hasattr(response, "usage_metadata"):
            try:
                from ad_engine.metrics.token_tracker import usage_from_response
                token_tracker.add_from_usage(usage_from_response(response))
            except Exception:
                pass
        text = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_json(text)
        if not parsed:
            return dict(DEFAULT_INSIGHTS)
        return {
            "hooks": isinstance(parsed.get("hooks"), list) and parsed["hooks"] or [],
            "ctas": isinstance(parsed.get("ctas"), list) and parsed["ctas"] or [],
            "tone_angles": isinstance(parsed.get("tone_angles"), list) and parsed["tone_angles"] or [],
        }
    except Exception as e:
        logger.warning("extract_patterns failed: %s", e)
        return dict(DEFAULT_INSIGHTS)


def rewrite_as_brand(ad: Dict, token_tracker=None) -> Optional[Dict]:
    """Rewrite competitor ad in Varsity Tutors brand. Returns ad dict or None."""
    from ad_engine.config import FALLBACK_AD
    if not ad:
        return dict(FALLBACK_AD)
    try:
        model = get_llm()
        ad_json = json.dumps(ad, indent=0)
        user = REWRITE_AS_BRAND_USER.format(ad_json=ad_json)
        response = with_retry(lambda: model.generate_content([REWRITE_AS_BRAND_SYSTEM, user]))
        if token_tracker and hasattr(response, "usage_metadata"):
            try:
                from ad_engine.metrics.token_tracker import usage_from_response
                token_tracker.add_from_usage(usage_from_response(response))
            except Exception:
                pass
        text = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_json(text)
        if not parsed:
            return None
        for key in ("primary_text", "headline", "description", "cta"):
            if key not in parsed or parsed[key] is None:
                parsed[key] = ad.get(key) or FALLBACK_AD.get(key, "")
        return parsed
    except Exception as e:
        logger.warning("rewrite_as_brand failed: %s", e)
        return None


def save_insights(insights: Dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(insights, f, indent=2)


def load_insights(path: Path) -> Dict:
    path = Path(path)
    if not path.exists():
        return dict(DEFAULT_INSIGHTS)
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_INSIGHTS)
        return {
            "hooks": data.get("hooks") if isinstance(data.get("hooks"), list) else [],
            "ctas": data.get("ctas") if isinstance(data.get("ctas"), list) else [],
            "tone_angles": data.get("tone_angles") if isinstance(data.get("tone_angles"), list) else [],
        }
    except Exception:
        return dict(DEFAULT_INSIGHTS)
