"""Tests for custom brief support — verifies that builder functions and
evaluation/generation respect custom brand_name in briefs."""

import pytest

from ad_engine.generate.prompt_templates import (
    AD_GENERATION_SYSTEM,
    DEFAULT_BRAND_VOICE,
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
        assert len(result) == 3
        assert "movie watchers" in result[0]
        assert "horror movie tickets" in result[1]
        assert "SAT" not in str(result)


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

    def test_default_clarity_unchanged(self):
        hint_default = get_improvement_hint("clarity")
        hint_custom = get_improvement_hint("clarity", brief=CUSTOM_BRIEF)
        # clarity has no custom override, so both use the default
        assert hint_default == hint_custom

    def test_no_brief_still_works(self):
        hint = get_improvement_hint("brand_voice", brief=None)
        assert "Varsity Tutors" in hint
