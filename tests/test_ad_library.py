"""Tests for storage.ad_library."""

import json
import tempfile
from pathlib import Path

import pytest
from ad_engine.storage.ad_library import AdLibrary


def test_add_and_list():
    lib = AdLibrary(base_path=tempfile.mkdtemp())
    lib.add(
        ad_id="ad_0",
        brief={"audience": "Parents"},
        ad_copy={"primary_text": "Test", "headline": "H", "description": "D", "cta": "Learn More"},
        scores={"clarity": 8, "value_proposition": 7, "cta": 8, "brand_voice": 7, "emotional_resonance": 7},
        overall_score=7.4,
        iteration_count=2,
    )
    ads = lib.list_ads()
    assert len(ads) == 1
    assert ads[0]["id"] == "ad_0"
    assert ads[0]["overall_score"] == 7.4
    assert ads[0]["ad_copy"]["primary_text"] == "Test"


def test_log_evaluation():
    lib = AdLibrary(base_path=tempfile.mkdtemp())
    lib.log_evaluation("ad_1", "clarity", 8, "Clear message.", "gemini-1.5")
    lib.add("ad_1", {}, {}, {}, 7.0, 1)
    lib.save(prefix="test")
    lib2 = AdLibrary(base_path=lib.base_path)
    lib2.load(prefix="test")
    assert len(lib2.list_ads()) == 1


def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        lib = AdLibrary(base_path=d)
        lib.add("x", {"a": 1}, {"primary_text": "P"}, {"clarity": 9}, 8.0, 1)
        lib.save(prefix="roundtrip")
        lib2 = AdLibrary(base_path=d)
        lib2.load(prefix="roundtrip")
        assert len(lib2) == 1
        assert lib2.list_ads()[0]["id"] == "x"
