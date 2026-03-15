"""Analyze top-performing ads from past runs and extract reusable patterns.

Mirrors the competitor/insights.py module pattern: gather data, LLM analysis,
save/load JSON.  Never raises; returns safe defaults on failure.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ad_engine.llm import get_llm
from ad_engine.utils import with_retry

logger = logging.getLogger(__name__)

DEFAULT_LEARNED_INSIGHTS: Dict[str, Any] = {
    "best_hooks": [],
    "best_ctas": [],
    "best_emotional_angles": [],
    "weak_dimensions": [],
    "golden_rules": [],
    "summary": "",
    "runs_analyzed": 0,
    "ads_analyzed": 0,
    "updated_at": "",
}

# ---------------------------------------------------------------------------
# Prompt templates for the learning analysis LLM call
# ---------------------------------------------------------------------------

LEARNING_ANALYSIS_SYSTEM = (
    "You analyze high-performing Facebook/Instagram ads and extract the patterns "
    "that made them score well on clarity, value proposition, CTA effectiveness, "
    "brand voice, and emotional resonance.  Be specific and actionable."
)

LEARNING_ANALYSIS_USER = (
    "Below are the top-scoring ads from past generation runs, with their "
    "per-dimension scores and evaluator rationales.\n\n"
    "{ads_json}\n\n"
    "Analyze these ads and extract the patterns that made them score well. "
    "Return ONLY a JSON object with these keys:\n"
    '- "best_hooks": array of 3-5 specific hook patterns/phrasings that scored highest\n'
    '- "best_ctas": array of 3-5 CTA patterns that worked best\n'
    '- "best_emotional_angles": array of 3-5 emotional approaches that resonated\n'
    '- "weak_dimensions": array of 2-3 objects like {{"dim": "...", "note": "..."}} '
    "for dimensions that tend to score lowest\n"
    '- "golden_rules": array of 3-5 concrete rules discovered from these top ads\n'
    '- "summary": 1-2 sentence summary of what makes ads score well\n\n'
    "Return ONLY the JSON object, no other text."
)

LEARNED_INSIGHTS_SNIPPET = (
    "\n\n## Learned from {runs_analyzed} past runs ({ads_analyzed} top ads analyzed):\n"
    "Best hooks: {best_hooks}\n"
    "Best CTAs: {best_ctas}\n"
    "Best emotional angles: {best_emotional_angles}\n"
    "Watch out for: {weak_dimensions}\n"
    "Golden rules: {golden_rules}\n"
    "Apply these learnings to generate higher-quality ads."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(text: str) -> Optional[Dict]:
    """Extract a JSON object from LLM output (same util as competitor/insights)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _ad_summary(ad: dict) -> dict:
    """Compact representation of an ad for the analysis prompt (saves tokens)."""
    copy = ad.get("ad_copy", ad)
    dims = ad.get("dimensions", {})
    scores = ad.get("scores", {})
    summary: Dict[str, Any] = {
        "headline": copy.get("headline", ""),
        "primary_text": (copy.get("primary_text", "") or "")[:200],
        "cta": copy.get("cta", ""),
        "overall_score": ad.get("overall_score", 0),
        "scores": scores,
    }
    # Include evaluator rationales — this is the richest signal for the LLM
    rationales = {}
    for dim, data in dims.items():
        if isinstance(data, dict) and data.get("rationale"):
            rationales[dim] = data["rationale"]
    if rationales:
        summary["rationales"] = rationales
    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def gather_top_ads(
    output_dir: Path,
    min_score: float = 6.0,
    max_ads: int = 20,
) -> List[dict]:
    """Walk output/runs/*/ads_dataset.json and collect top-scoring ads.

    Human votes influence learning:
    - Downvoted ads are excluded regardless of score.
    - Upvoted ads get a sort boost so they're prioritised as learning examples.
    """
    output_dir = Path(output_dir)
    runs_dir = output_dir / "runs"
    if not runs_dir.exists():
        return []

    all_ads: List[dict] = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        ads_path = run_dir / "ads_dataset.json"
        if not ads_path.exists():
            continue
        try:
            with open(ads_path) as f:
                ads = json.load(f)
            if not isinstance(ads, list):
                continue
            for ad in ads:
                # Skip downvoted ads — human said "not good"
                if ad.get("user_vote") == "down":
                    continue
                score = ad.get("overall_score", 0)
                if score >= min_score:
                    all_ads.append(ad)
        except Exception:
            continue

    # Sort descending by score; upvoted ads get a +1.0 boost for sort priority
    # (boost is only for ranking, not stored)
    def _sort_key(a):
        s = a.get("overall_score", 0)
        if a.get("user_vote") == "up":
            s += 1.0
        return s

    all_ads.sort(key=_sort_key, reverse=True)
    return all_ads[:max_ads]


def analyze_learnings(
    top_ads: List[dict],
    token_tracker=None,
) -> Dict[str, Any]:
    """Single LLM call to extract patterns from top ads. Returns insights dict."""
    if not top_ads:
        return dict(DEFAULT_LEARNED_INSIGHTS)
    try:
        model = get_llm()
        # Compact representations to save tokens
        summaries = [_ad_summary(ad) for ad in top_ads]
        ads_json = json.dumps(summaries, indent=0)[:12000]
        user = LEARNING_ANALYSIS_USER.format(ads_json=ads_json)

        response = with_retry(lambda: model.generate_content([LEARNING_ANALYSIS_SYSTEM, user]))

        if token_tracker and hasattr(response, "usage_metadata"):
            try:
                from ad_engine.metrics.token_tracker import usage_from_response
                token_tracker.add_from_usage(usage_from_response(response))
            except Exception:
                pass

        text = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_json(text)
        if not parsed:
            logger.warning("Learning analysis: could not parse LLM response")
            return dict(DEFAULT_LEARNED_INSIGHTS)

        # Normalize and validate each field
        def _list_of_str(val: Any) -> List[str]:
            if isinstance(val, list):
                return [str(v) for v in val if v][:5]
            return []

        def _list_of_dim(val: Any) -> List[Dict[str, str]]:
            if isinstance(val, list):
                result = []
                for v in val[:3]:
                    if isinstance(v, dict):
                        result.append({"dim": str(v.get("dim", "")), "note": str(v.get("note", ""))})
                    elif isinstance(v, str):
                        result.append({"dim": v, "note": ""})
                return result
            return []

        return {
            "best_hooks": _list_of_str(parsed.get("best_hooks")),
            "best_ctas": _list_of_str(parsed.get("best_ctas")),
            "best_emotional_angles": _list_of_str(parsed.get("best_emotional_angles")),
            "weak_dimensions": _list_of_dim(parsed.get("weak_dimensions")),
            "golden_rules": _list_of_str(parsed.get("golden_rules")),
            "summary": str(parsed.get("summary", "")),
            "runs_analyzed": 0,  # filled by caller
            "ads_analyzed": len(top_ads),
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.warning("analyze_learnings failed: %s", e)
        return dict(DEFAULT_LEARNED_INSIGHTS)


def save_learned_insights(insights: Dict, path: Path) -> None:
    """Persist learned insights to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(insights, f, indent=2)


def load_learned_insights(path: Path) -> Dict[str, Any]:
    """Load learned insights from JSON; return safe default if not found."""
    path = Path(path)
    if not path.exists():
        return dict(DEFAULT_LEARNED_INSIGHTS)
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_LEARNED_INSIGHTS)
        return {
            "best_hooks": data.get("best_hooks") if isinstance(data.get("best_hooks"), list) else [],
            "best_ctas": data.get("best_ctas") if isinstance(data.get("best_ctas"), list) else [],
            "best_emotional_angles": data.get("best_emotional_angles") if isinstance(data.get("best_emotional_angles"), list) else [],
            "weak_dimensions": data.get("weak_dimensions") if isinstance(data.get("weak_dimensions"), list) else [],
            "golden_rules": data.get("golden_rules") if isinstance(data.get("golden_rules"), list) else [],
            "summary": str(data.get("summary", "")),
            "runs_analyzed": data.get("runs_analyzed", 0),
            "ads_analyzed": data.get("ads_analyzed", 0),
            "updated_at": data.get("updated_at", ""),
        }
    except Exception:
        return dict(DEFAULT_LEARNED_INSIGHTS)


def format_learned_snippet(insights: Dict) -> str:
    """Format insights dict into a prompt snippet for injection into system prompt."""
    weak_dims = insights.get("weak_dimensions") or []
    weak_str = ", ".join(
        (d["dim"] + ": " + d["note"]) if isinstance(d, dict) else str(d)
        for d in weak_dims[:3]
    ) or "N/A"

    return LEARNED_INSIGHTS_SNIPPET.format(
        runs_analyzed=insights.get("runs_analyzed", 0),
        ads_analyzed=insights.get("ads_analyzed", 0),
        best_hooks=", ".join((insights.get("best_hooks") or [])[:5]) or "N/A",
        best_ctas=", ".join((insights.get("best_ctas") or [])[:5]) or "N/A",
        best_emotional_angles=", ".join((insights.get("best_emotional_angles") or [])[:5]) or "N/A",
        weak_dimensions=weak_str,
        golden_rules="; ".join((insights.get("golden_rules") or [])[:5]) or "N/A",
    )
