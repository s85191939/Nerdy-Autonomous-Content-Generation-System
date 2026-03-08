"""Tests for evaluator confidence scoring (Excellent rubric)."""

import pytest
from ad_engine.evaluate.dimension_scorer import _parse_evaluation, _aggregate_confidence
from ad_engine.config import DIMENSION_NAMES


def test_parse_evaluation_includes_confidence():
    text = '''{"clarity": {"score": 8, "rationale": "Clear.", "confidence": 9},
               "value_proposition": {"score": 7, "rationale": "OK", "confidence": 6},
               "cta": {"score": 9, "rationale": "Strong", "confidence": 8},
               "brand_voice": {"score": 8, "rationale": "On-brand", "confidence": 7},
               "emotional_resonance": {"score": 7, "rationale": "Good", "confidence": 5}}'''
    out = _parse_evaluation(text)
    assert out["clarity"]["confidence"] == 9
    assert out["emotional_resonance"]["confidence"] == 5


def test_parse_evaluation_confidence_defaults_when_missing():
    text = '''{"clarity": {"score": 8, "rationale": "Clear."},
               "value_proposition": {"score": 7}, "cta": {"score": 7},
               "brand_voice": {"score": 7}, "emotional_resonance": {"score": 7}}'''
    out = _parse_evaluation(text)
    assert out["clarity"]["confidence"] == 5  # default


def test_aggregate_confidence():
    dim_results = {d: {"score": 8, "rationale": "", "confidence": 6 + (i % 3)} for i, d in enumerate(DIMENSION_NAMES)}
    agg = _aggregate_confidence(dim_results)
    assert 5 <= agg <= 8
