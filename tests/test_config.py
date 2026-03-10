"""Tests for config."""

import pytest
from ad_engine.config import (
    QUALITY_THRESHOLD,
    MAX_ITERATIONS,
    DIMENSION_WEIGHTS,
    DIMENSION_NAMES,
    FALLBACK_AD,
)


def test_quality_threshold():
    assert QUALITY_THRESHOLD == 7.0


def test_max_iterations():
    assert MAX_ITERATIONS >= 3


def test_dimension_weights_sum_to_one():
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001


def test_dimension_names_count():
    assert len(DIMENSION_NAMES) == 5


def test_dimension_weights_keys_match_names():
    assert set(DIMENSION_WEIGHTS.keys()) == set(DIMENSION_NAMES)


def test_fallback_ad_has_required_keys():
    """FALLBACK_AD is used when generation fails; must have all ad copy keys."""
    required = {"primary_text", "headline", "description", "cta"}
    assert set(FALLBACK_AD.keys()) == required
    for k in required:
        assert isinstance(FALLBACK_AD[k], str), f"FALLBACK_AD.{k} must be string"
        assert len(FALLBACK_AD[k]) > 0, f"FALLBACK_AD.{k} must be non-empty"
