"""Tests for output.export_reports."""

import csv
import json
import tempfile
from pathlib import Path

import pytest
from ad_engine.output.export_reports import export_ads_dataset, export_evaluation_report, export_evaluation_summary
from ad_engine.config import DIMENSION_NAMES


@pytest.fixture
def sample_ads():
    return [
        {
            "id": "ad_0",
            "overall_score": 7.8,
            "iteration_count": 2,
            "scores": {"clarity": 8, "value_proposition": 7, "cta": 9, "brand_voice": 8, "emotional_resonance": 7},
        },
        {
            "id": "ad_1",
            "overall_score": 6.5,
            "iteration_count": 4,
            "scores": {"clarity": 7, "value_proposition": 6, "cta": 7, "brand_voice": 6, "emotional_resonance": 6},
        },
    ]


def test_export_ads_dataset(sample_ads):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ads.json"
        export_ads_dataset(sample_ads, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 2
        assert data[0]["id"] == "ad_0"


def test_export_evaluation_report(sample_ads):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "report.csv"
        export_evaluation_report(sample_ads, path)
        assert path.exists()
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert "ad_id" in rows[0]
        assert "overall_score" in rows[0]
        for dim in DIMENSION_NAMES:
            assert dim in rows[0]


def test_export_evaluation_summary():
    from ad_engine.output.export_reports import export_evaluation_summary
    ads = [
        {"id": "ad_0", "overall_score": 7.5, "iteration_count": 2, "accepted": True},
        {"id": "ad_1", "overall_score": 6.5, "iteration_count": 4, "accepted": False},
    ]
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "summary.txt"
        export_evaluation_summary(ads, path, quality_threshold=7.0)
        assert path.exists()
        text = path.read_text()
        assert "Total ads generated: 2"
        assert "1 (50.0%)" in text or "50.0%" in text
        assert "7.00" in text or "7.0" in text
