"""Tests for custom brief support and Meta ad structure calibration.

Verifies that builder functions and evaluation/generation respect:
1. Custom brand_name in briefs (custom vs Varsity Tutors default).
2. Meta ad copy structure (hook ≤125 chars, headline 5-8 words, funnel-matched CTA).
3. PDF-inspired creative patterns (6 hook types, proven creative best practices).
"""

import pytest

from ad_engine.generate.prompt_templates import (
    AD_GENERATION_SYSTEM,
    DEFAULT_BRAND_VOICE,
    HOOK_PATTERNS,
    META_AD_STRUCTURE,
    VARIANT_ANGLES,
    build_ad_generation_system,
    build_brand_voice,
    build_variant_angles,
)
from ad_engine.evaluate.dimension_scorer import (
    EVALUATION_SYSTEM,
    build_evaluation_system,
)
from ad_engine.creative.visual_evaluator import (
    VISUAL_EVAL_SYSTEM,
    build_visual_eval_system,
)
from ad_engine.iterate.improvement_strategies import get_improvement_hint


CUSTOM_BRIEF = {
    "brand_name": "MovieMagic",
    "audience": "movie watchers",
    "product": "horror movie tickets",
    "goal": "buy tickets",
    "tone": "commanding, thrilling",
}

DEFAULT_BRIEF = {
    "audience": "Parents of high school students",
    "product": "SAT tutoring program",
    "goal": "conversion",
    "tone": "reassuring, results-focused",
}


# --- prompt_templates builders ---


class TestBuildBrandVoice:
    def test_default_when_none(self):
        assert build_brand_voice(None) == DEFAULT_BRAND_VOICE

    def test_default_when_no_brand_name(self):
        assert build_brand_voice(DEFAULT_BRIEF) == DEFAULT_BRAND_VOICE

    def test_custom_brand(self):
        result = build_brand_voice(CUSTOM_BRIEF)
        assert "MovieMagic" in result
        assert "Varsity Tutors" not in result
        assert "movie watchers" in result


class TestBuildAdGenerationSystem:
    def test_default_when_none(self):
        assert build_ad_generation_system(None) == AD_GENERATION_SYSTEM

    def test_default_when_no_brand_name(self):
        assert build_ad_generation_system(DEFAULT_BRIEF) == AD_GENERATION_SYSTEM

    def test_custom_brand(self):
        result = build_ad_generation_system(CUSTOM_BRIEF)
        assert "MovieMagic" in result
        assert "horror movie tickets" in result
        assert "Varsity Tutors" not in result
        assert "SAT" not in result
        # Still has Meta ad format instructions
        assert "primary_text" in result
        assert "headline" in result

    def test_custom_brand_empty_string(self):
        brief = {**CUSTOM_BRIEF, "brand_name": ""}
        assert build_ad_generation_system(brief) == AD_GENERATION_SYSTEM


class TestBuildVariantAngles:
    def test_default_when_none(self):
        assert build_variant_angles(None) == VARIANT_ANGLES

    def test_default_when_no_brand_name(self):
        assert build_variant_angles(DEFAULT_BRIEF) == VARIANT_ANGLES

    def test_custom_brand(self):
        result = build_variant_angles(CUSTOM_BRIEF)
        assert len(result) == 6  # 6 hook types: question, stat, story, bold claim, pain point, curiosity gap
        assert "movie watchers" in result[0]
        assert "horror movie tickets" in result[1]
        assert "SAT" not in str(result)
        # All 6 hook types present
        all_text = " ".join(result).upper()
        assert "QUESTION" in all_text
        assert "STAT" in all_text or "NUMBER" in all_text
        assert "STORY" in all_text or "TESTIMONIAL" in all_text
        assert "BOLD CLAIM" in all_text
        assert "PAIN POINT" in all_text
        assert "CURIOSITY" in all_text


# --- dimension_scorer builder ---


class TestBuildEvaluationSystem:
    def test_default_when_none(self):
        assert build_evaluation_system(None) == EVALUATION_SYSTEM

    def test_default_when_no_brand_name(self):
        assert build_evaluation_system(DEFAULT_BRIEF) == EVALUATION_SYSTEM

    def test_custom_brand(self):
        result = build_evaluation_system(CUSTOM_BRIEF)
        assert "MovieMagic" in result
        assert "commanding, thrilling" in result
        assert "horror movie tickets" in result
        assert "movie watchers" in result
        assert "Varsity Tutors" not in result
        assert "SAT" not in result
        # Still has all 5 dimensions
        assert "clarity" in result
        assert "value_proposition" in result
        assert "cta" in result
        assert "brand_voice" in result
        assert "emotional_resonance" in result


# --- visual_evaluator builder ---


class TestBuildVisualEvalSystem:
    def test_default_when_none(self):
        assert build_visual_eval_system(None) == VISUAL_EVAL_SYSTEM

    def test_default_when_no_brand_name(self):
        assert build_visual_eval_system(DEFAULT_BRIEF) == VISUAL_EVAL_SYSTEM

    def test_custom_brand(self):
        result = build_visual_eval_system(CUSTOM_BRIEF)
        assert "MovieMagic" in result
        assert "commanding, thrilling" in result
        assert "Varsity Tutors" not in result


# --- improvement_strategies ---


class TestGetImprovementHint:
    def test_default_brand_voice(self):
        hint = get_improvement_hint("brand_voice")
        assert "Varsity Tutors" in hint

    def test_custom_brand_voice(self):
        hint = get_improvement_hint("brand_voice", brief=CUSTOM_BRIEF)
        assert "MovieMagic" in hint
        assert "commanding, thrilling" in hint
        assert "Varsity Tutors" not in hint

    def test_custom_emotional_resonance(self):
        hint = get_improvement_hint("emotional_resonance", brief=CUSTOM_BRIEF)
        assert "movie watchers" in hint

    def test_custom_value_proposition(self):
        hint = get_improvement_hint("value_proposition", brief=CUSTOM_BRIEF)
        assert "horror movie tickets" in hint

    def test_custom_clarity(self):
        hint = get_improvement_hint("clarity", brief=CUSTOM_BRIEF)
        # custom clarity has Meta-specific guidance
        assert "125" in hint  # ≤125 char first-line hook
        assert "hook" in hint.lower()

    def test_custom_cta(self):
        hint = get_improvement_hint("cta", brief=CUSTOM_BRIEF)
        # custom CTA has funnel-matched guidance
        assert "funnel" in hint.lower() or "Learn More" in hint

    def test_no_brief_still_works(self):
        hint = get_improvement_hint("brand_voice", brief=None)
        assert "Varsity Tutors" in hint

    def test_default_hints_have_meta_guidance(self):
        """Default improvement hints should reference Meta ad structure."""
        clarity = get_improvement_hint("clarity")
        assert "125" in clarity  # ≤125 char hook
        vp = get_improvement_hint("value_proposition")
        assert "5" in vp and "8" in vp  # 5-8 word headline
        cta = get_improvement_hint("cta")
        assert "Learn More" in cta  # funnel-matched CTA examples


# --- Meta ad structure calibration ---


class TestMetaAdStructureCalibration:
    """Verify that generation and evaluation prompts enforce Meta ad copy structure."""

    def test_generation_system_has_meta_structure(self):
        assert "125" in AD_GENERATION_SYSTEM  # ≤125 char first-line hook
        assert "5" in AD_GENERATION_SYSTEM and "8" in AD_GENERATION_SYSTEM  # 5-8 word headline
        assert "Learn More" in AD_GENERATION_SYSTEM  # CTA examples
        assert "primary_text" in AD_GENERATION_SYSTEM
        assert "headline" in AD_GENERATION_SYSTEM

    def test_generation_system_has_hook_types(self):
        """All 6 proven hook types should be in the generation system prompt."""
        upper = AD_GENERATION_SYSTEM.upper()
        assert "QUESTION HOOK" in upper
        assert "STAT" in upper or "NUMBER HOOK" in upper
        assert "STORY" in upper or "TESTIMONIAL HOOK" in upper
        assert "BOLD CLAIM HOOK" in upper
        assert "PAIN POINT HOOK" in upper
        assert "CURIOSITY GAP HOOK" in upper

    def test_evaluation_system_has_meta_penalties(self):
        """Evaluation prompt should enforce Meta structure penalties."""
        assert "125" in EVALUATION_SYSTEM  # first-line ≤125 chars
        assert "cap clarity" in EVALUATION_SYSTEM.lower() or "cap" in EVALUATION_SYSTEM.lower()
        assert "funnel" in EVALUATION_SYSTEM.lower()

    def test_evaluation_system_has_meta_criteria(self):
        """Evaluation should judge against Meta-specific criteria."""
        assert "benefit-driven" in EVALUATION_SYSTEM.lower() or "benefit" in EVALUATION_SYSTEM.lower()
        assert "hook" in EVALUATION_SYSTEM.lower()

    def test_variant_angles_cover_six_hooks(self):
        """Default VARIANT_ANGLES should offer 6 hook types for A/B diversity."""
        assert len(VARIANT_ANGLES) == 6
        all_text = " ".join(VARIANT_ANGLES).upper()
        assert "QUESTION" in all_text
        assert "STAT" in all_text
        assert "STORY" in all_text or "TESTIMONIAL" in all_text
        assert "BOLD CLAIM" in all_text
        assert "PAIN POINT" in all_text
        assert "CURIOSITY" in all_text

    def test_custom_generation_has_meta_structure(self):
        result = build_ad_generation_system(CUSTOM_BRIEF)
        assert "125" in result  # ≤125 char hook
        assert "5" in result  # 5-8 words
        assert "Learn More" in result  # CTA examples
        assert "QUESTION HOOK" in result.upper()
        assert "CURIOSITY GAP HOOK" in result.upper()

    def test_custom_evaluation_has_meta_penalties(self):
        result = build_evaluation_system(CUSTOM_BRIEF)
        assert "125" in result
        assert "cap" in result.lower()
        assert "funnel" in result.lower()
