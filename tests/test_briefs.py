"""Tests for generate.briefs."""

import pytest
from ad_engine.generate.briefs import DEFAULT_BRIEFS, get_briefs_for_count


def test_default_briefs_structure():
    for b in DEFAULT_BRIEFS:
        assert "audience" in b
        assert "product" in b
        assert "goal" in b
        assert "tone" in b


def test_get_briefs_for_count_small():
    briefs = get_briefs_for_count(3)
    assert len(briefs) == 3


def test_get_briefs_for_count_large():
    briefs = get_briefs_for_count(50)
    assert len(briefs) == 50


def test_get_briefs_for_count_reproducible_with_seed():
    a = get_briefs_for_count(15, seed=42)
    b = get_briefs_for_count(15, seed=42)
    assert a == b


def test_get_briefs_for_count_deterministic_order_with_seed():
    briefs = get_briefs_for_count(5, seed=123)
    assert len(briefs) == 5
    assert all("audience" in b for b in briefs)
