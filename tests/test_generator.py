"""Tests for generator JSON parsing (no API calls)."""

import pytest
from ad_engine.generate.generator import _parse_json_from_response


def test_parse_json_simple():
    text = '{"primary_text": "Hello", "headline": "H", "description": "D", "cta": "Learn More"}'
    out = _parse_json_from_response(text)
    assert out["primary_text"] == "Hello"
    assert out["cta"] == "Learn More"


def test_parse_json_with_markdown():
    text = 'Here is the ad:\n```json\n{"primary_text": "Hi", "headline": "H", "description": "", "cta": "Sign Up"}\n```'
    out = _parse_json_from_response(text)
    assert out["primary_text"] == "Hi"
    assert out["cta"] == "Sign Up"


def test_parse_json_nested():
    # Parser handles JSON with commas and extra text (e.g. from LLM output)
    text = 'Ad copy: {"primary_text": "Raise your score", "headline": "H", "description": "D", "cta": "C"}'
    out = _parse_json_from_response(text)
    assert "primary_text" in out
    assert "Raise your score" in out["primary_text"]
