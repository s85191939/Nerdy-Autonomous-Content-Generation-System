"""Tests for evaluate.aggregator."""

import pytest
from ad_engine.evaluate.aggregator import aggregate_scores
from ad_engine.config import DIMENSION_WEIGHTS


def test_aggregate_scores_all_present():
    scores = {
        "clarity": 8,
        "value_proposition": 7,
        "cta": 9,
        "brand_voice": 8,
        "emotional_resonance": 7,
    }
    out = aggregate_scores(scores)
    assert 7 <= out <= 9
    # Weighted: 0.25*8 + 0.25*7 + 0.15*9 + 0.15*8 + 0.20*7 = 2+1.75+1.35+1.2+1.4 = 7.7
    assert abs(out - 7.7) < 0.01


def test_aggregate_scores_partial():
    # Only clarity and value_proposition (weight 0.25 each); total weight 0.5
    # (0.25*10 + 0.25*10) / 0.5 = 10.0
    scores = {"clarity": 10, "value_proposition": 10}
    out = aggregate_scores(scores)
    assert out == 10.0


def test_aggregate_scores_empty():
    assert aggregate_scores({}) == 0.0


def test_aggregate_scores_float():
    scores = {"clarity": 7.5, "value_proposition": 8.0, "cta": 6.0, "brand_voice": 7.0, "emotional_resonance": 7.0}
    out = aggregate_scores(scores)
    assert isinstance(out, float)
    assert 6 <= out <= 8
