"""Ad copy generator using Gemini or OpenRouter from structured briefs."""

import json
import logging
import os
import re
from typing import List, Optional

from dotenv import load_dotenv

from ad_engine.config import FALLBACK_AD
from ad_engine.generate.prompt_templates import (
    AD_GENERATION_SYSTEM,
    AD_GENERATION_USER,
    IMPROVEMENT_USER,
    REFERENCE_PATTERNS_SNIPPET,
    VARIANT_ANGLES,
    build_ad_generation_system,
)
from ad_engine.llm import get_llm
from ad_engine.metrics.token_tracker import usage_from_response
from ad_engine.utils import with_retry

load_dotenv()
logger = logging.getLogger(__name__)


def _get_client():
    return get_llm()


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_json_from_response(text: str) -> dict:
    """Extract a single JSON object from model output."""
    text = _strip_markdown_fences(text)
    # Try to find {...}
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _parse_json_array_from_response(text: str, expected_count: int) -> List[dict]:
    """Extract a JSON array of objects from model output."""
    text = _strip_markdown_fences(text)
    # Try to find [...]
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            logger.warning("JSON array parse failed, trying individual objects")
    # Fallback: try to find individual objects
    objects = []
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL):
        try:
            objects.append(json.loads(m.group()))
        except json.JSONDecodeError:
            continue
    return objects


def _enforce_primary_text_length(ad: dict, max_visible: int = 125) -> None:
    """Store full primary text; add a truncated preview for Meta's visible portion."""
    pt = (ad.get("primary_text") or "").strip()
    if not pt:
        return
    # Always keep the full text — never truncate the actual copy
    ad["primary_text"] = pt
    # Store a preview field for reference (Meta shows ~125 chars before "...See More")
    if len(pt) > max_visible:
        ad["primary_text_preview"] = pt[: max_visible - 3].rstrip() + "..."


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
        system = build_ad_generation_system(brief)
        insights = reference_insights if reference_insights is not None else getattr(self, "_reference_insights", None)
        if insights and isinstance(insights, dict):
            hooks = insights.get("hooks") or []
            ctas = insights.get("ctas") or []
            angles = insights.get("tone_angles") or []
            if hooks or ctas or angles:
                snippet = REFERENCE_PATTERNS_SNIPPET.format(hooks=", ".join(hooks[:5]) or "N/A", ctas=", ".join(ctas[:5]) or "N/A", tone_angles=", ".join(angles[:4]) or "N/A")
                system = system + snippet
        creative_angle_suffix = ("\nCreative approach for this variant: " + creative_angle) if creative_angle else ""
        additional_context = brief.get("additional_context", "")
        additional_context_suffix = ("\n\nIMPORTANT — The user gave these specific creative directions (you MUST follow them):\n" + additional_context) if additional_context else ""
        user = AD_GENERATION_USER.format(
            audience=brief.get("audience", "Parents of high school students"),
            product=brief.get("product", "SAT tutoring program"),
            goal=brief.get("goal", "conversion"),
            tone=brief.get("tone", "reassuring, results-focused"),
            creative_angle_suffix=creative_angle_suffix,
            additional_context_suffix=additional_context_suffix,
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

    def generate_batch(self, briefs: List[dict], count: int = None) -> List[dict]:
        """Generate multiple ads in a SINGLE LLM call. Returns list of ad dicts.
        If all briefs are identical (same brief repeated), generates `count` unique variations.
        Falls back to parallel individual generation on failure."""
        if not briefs:
            return []
        n = count or len(briefs)
        try:
            result = self._generate_batch_impl(briefs, n)
            # Verify we got real ads, not empty results
            valid = [ad for ad in result if ad.get("headline") and ad["headline"] != FALLBACK_AD["headline"]]
            if len(valid) >= n // 2:
                return result
            logger.warning("Batch generation returned %d/%d valid ads, falling back", len(valid), n)
        except Exception as e:
            logger.warning("Batch generation failed: %s — falling back to parallel individual", e)
        # Parallel individual fallback
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(n, 8)) as executor:
            futures = [executor.submit(self.generate, briefs[i % len(briefs)]) for i in range(n)]
            return [f.result() for f in futures]

    def _generate_batch_impl(self, briefs: List[dict], n: int) -> List[dict]:
        """Generate N ads in one LLM call."""
        # Use first brief for system prompt (all briefs should share brand)
        brief = briefs[0]
        system = build_ad_generation_system(brief)
        insights = getattr(self, "_reference_insights", None)
        if insights and isinstance(insights, dict):
            hooks = insights.get("hooks") or []
            ctas = insights.get("ctas") or []
            angles = insights.get("tone_angles") or []
            if hooks or ctas or angles:
                snippet = REFERENCE_PATTERNS_SNIPPET.format(
                    hooks=", ".join(hooks[:5]) or "N/A",
                    ctas=", ".join(ctas[:5]) or "N/A",
                    tone_angles=", ".join(angles[:4]) or "N/A",
                )
                system = system + snippet

        user = f"""Audience: {brief.get("audience", "Parents of high school students")}
Product/offer: {brief.get("product", "SAT tutoring program")}
Goal: {brief.get("goal", "conversion")}
Tone: {brief.get("tone", "reassuring, results-focused")}

Generate exactly {n} UNIQUE Facebook/Instagram ads. Each ad must use a DIFFERENT hook type.
Return a JSON array of {n} objects. Each object has keys: primary_text, headline, description, cta.
Return ONLY the JSON array, no other text."""

        def _call():
            return self._model.generate_content(
                [system, user],
                generation_config=self._generation_config,
            )

        response = with_retry(_call)
        if self._token_tracker:
            self._token_tracker.add_from_usage(usage_from_response(response))
        text = response.text if hasattr(response, "text") else str(response)
        ads = _parse_json_array_from_response(text, n)

        # Validate and pad if needed
        result = []
        for i in range(n):
            if i < len(ads) and isinstance(ads[i], dict):
                ad = ads[i]
                for key in ("primary_text", "headline", "description", "cta"):
                    if key not in ad or ad[key] is None:
                        ad[key] = FALLBACK_AD.get(key, "")
                _enforce_primary_text_length(ad)
                result.append(ad)
            else:
                result.append(dict(FALLBACK_AD))
        return result

    def improve(
        self,
        ad: dict,
        weak_dimension: str,
        rationale: str,
        brief: dict = None,
        user_context: str = None,
    ) -> dict:
        """Regenerate ad with targeted improvement for weak_dimension."""
        try:
            return self._improve_impl(ad, weak_dimension, rationale, brief=brief, user_context=user_context)
        except Exception as e:
            logger.warning("Ad improvement failed, returning original ad: %s", e)
            return dict(ad) if ad else dict(FALLBACK_AD)

    def _improve_impl(
        self,
        ad: dict,
        weak_dimension: str,
        rationale: str,
        brief: dict = None,
        user_context: str = None,
    ) -> dict:
        """Internal improve; may raise."""
        system = build_ad_generation_system(brief)
        user_context_suffix = ""
        if user_context:
            user_context_suffix = "\nUser instructions: " + user_context
        user = IMPROVEMENT_USER.format(
            ad_json=json.dumps(ad, indent=2),
            weak_dimension=weak_dimension.replace("_", " ").title(),
            rationale=rationale,
            user_context_suffix=user_context_suffix,
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
        for key in ("primary_text", "headline", "description", "cta"):
            if key not in parsed or parsed[key] is None:
                parsed[key] = (ad or FALLBACK_AD).get(key, "")
        _enforce_primary_text_length(parsed)
        return parsed
