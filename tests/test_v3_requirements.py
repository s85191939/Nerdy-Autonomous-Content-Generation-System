"""Tests for v3 spec requirements: self-healing, quality ratchet, agents, competitive intel."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_v3_self_heal_detect_quality_drop():
    """v3: Self-healing — detect quality drop vs previous run."""
    from ad_engine.metrics.self_heal import detect_quality_drop, load_run_history
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "run_history.json"
        path.write_text(json.dumps([
            {"run_id": "r1", "avg_score": 7.5},
            {"run_id": "r2", "avg_score": 6.8},
        ]))
        dropped, msg = detect_quality_drop(6.0, path, min_runs_to_compare=1)
        assert dropped is True
        assert "drop" in msg.lower() or "6.0" in msg
        dropped2, _ = detect_quality_drop(7.2, path, min_runs_to_compare=1)
        assert dropped2 is False


def test_v3_quality_ratchet_best_avg():
    """v3: Quality ratchet — best avg score so far, standards only go UP."""
    from ad_engine.metrics.quality_ratchet import best_avg_score_so_far, quality_floor_for_run, apply_ratchet_to_summary
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "run_history.json"
        path.write_text(json.dumps([
            {"avg_score": 7.2},
            {"avg_score": 7.8},
            {"avg_score": 7.5},
        ]))
        assert best_avg_score_so_far(path) == 7.8
        floor = quality_floor_for_run(path, default_floor=7.0)
        assert floor >= 7.0
        lines = apply_ratchet_to_summary(path, ["Line 1"], default_threshold=7.0)
        joined = "".join(lines)
        assert "ratchet" in joined.lower() and "7.80" in joined


def test_v3_agents_orchestration():
    """v3: Agentic orchestration — Researcher, Writer, Editor, Evaluator agents exist and run_for_brief_agentic runs."""
    from ad_engine.agents import ResearcherAgent, WriterAgent, EditorAgent, EvaluatorAgent, run_for_brief_agentic
    from ad_engine.generate import AdGenerator
    from ad_engine.evaluate import Evaluator
    researcher = ResearcherAgent()
    gen = MagicMock()
    gen.generate.return_value = {"primary_text": "P", "headline": "H", "description": "D", "cta": "CTA"}
    gen.improve.return_value = {"primary_text": "P2", "headline": "H2", "description": "D2", "cta": "CTA2"}
    writer = WriterAgent(gen)
    editor = EditorAgent(gen)
    ev = MagicMock()
    ev.evaluate.return_value = {
        "scores": {d: 8 for d in ["clarity", "value_proposition", "cta", "brand_voice", "emotional_resonance"]},
        "dimensions": {d: {"score": 8, "rationale": "Ok", "confidence": 8} for d in ["clarity", "value_proposition", "cta", "brand_voice", "emotional_resonance"]},
        "overall_score": 8.0,
        "confidence": 8.0,
    }
    evaluator_agent = EvaluatorAgent(ev)
    brief = {"audience": "P", "product": "S", "goal": "c", "tone": "warm"}
    result = run_for_brief_agentic(brief, researcher, writer, editor, evaluator_agent, quality_threshold=7.0, max_iterations=3)
    assert result["accepted"] is True
    assert result["iteration_count"] == 1
    assert "ad" in result and "evaluation" in result


def test_v3_competitive_intel_script_exists():
    """v3: Competitive intelligence — script exists for Meta Ad Library ads."""
    script = REPO_ROOT / "scripts" / "run_competitive_intel.py"
    assert script.exists()
    content = script.read_text()
    assert "extract_patterns" in content or "competitive" in content.lower()
    assert "ads_json" in content or "ads.json" in content
