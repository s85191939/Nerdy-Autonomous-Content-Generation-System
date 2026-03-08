"""Tests for iterate.improvement_strategies and optimizer."""

import pytest
from unittest.mock import MagicMock

from ad_engine.iterate.improvement_strategies import get_improvement_hint
from ad_engine.config import DIMENSION_NAMES


def test_improvement_hint_all_dimensions():
    for dim in DIMENSION_NAMES:
        hint = get_improvement_hint(dim)
        assert isinstance(hint, str)
        assert len(hint) > 0


def test_improvement_hint_unknown_dimension():
    hint = get_improvement_hint("unknown_dim")
    assert "unknown_dim" in hint or "Improve" in hint


def test_weakest_dimension_logic():
    from ad_engine.iterate.optimizer import _weakest_dimension
    scores = {"clarity": 8, "value_proposition": 5, "cta": 7, "brand_voice": 6, "emotional_resonance": 7}
    assert _weakest_dimension(scores) == "value_proposition"


def test_iteration_engine_accepts_high_score():
    from ad_engine.iterate.optimizer import IterationEngine
    gen = MagicMock()
    gen.generate.return_value = {"primary_text": "P", "headline": "H", "description": "D", "cta": "Learn More"}
    gen.improve.return_value = gen.generate.return_value
    ev = MagicMock()
    ev.evaluate.return_value = {
        "scores": {d: 8 for d in ["clarity", "value_proposition", "cta", "brand_voice", "emotional_resonance"]},
        "dimensions": {d: {"score": 8, "rationale": "Ok", "confidence": 8} for d in ["clarity", "value_proposition", "cta", "brand_voice", "emotional_resonance"]},
        "overall_score": 8.0,
        "confidence": 8.0,
    }
    engine = IterationEngine(generator=gen, evaluator=ev, quality_threshold=7.0, max_iterations=5)
    result = engine.run_for_brief({"audience": "Parents", "product": "SAT", "goal": "conversion", "tone": "warm"})
    assert result["accepted"] is True
    assert result["iteration_count"] == 1
    gen.generate.assert_called_once()
    gen.improve.assert_not_called()
