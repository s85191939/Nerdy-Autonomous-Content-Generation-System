"""Tests for metrics.performance_metrics."""

import pytest
from ad_engine.metrics.performance_metrics import PerformanceMetrics


def test_record_run_and_performance_per_token():
    m = PerformanceMetrics()
    m.record_run(cycle=1, avg_score=6.2, token_cost=2.0, num_ads=10)
    m.record_run(cycle=2, avg_score=7.1, token_cost=2.2, num_ads=10)
    assert m.performance_per_token() == pytest.approx(7.1 / 2.2, rel=0.01)
    assert m.performance_per_token(cycle=1) == pytest.approx(6.2 / 2.0, rel=0.01)


def test_quality_trend():
    m = PerformanceMetrics()
    m.record_run(1, 6.0, 1.0, 5)
    m.record_run(2, 7.0, 1.0, 5)
    m.record_run(3, 7.5, 1.0, 5)
    assert m.quality_trend() == [6.0, 7.0, 7.5]


def test_empty_runs():
    m = PerformanceMetrics()
    assert m.performance_per_token() == 0.0
    assert m.quality_trend() == []


def test_zero_token_cost():
    m = PerformanceMetrics()
    m.record_run(1, 7.0, 0.0, 10)
    assert m.performance_per_token() == 0.0
