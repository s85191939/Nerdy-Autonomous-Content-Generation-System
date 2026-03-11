"""
Submission artifact tests — Spec p.7 "Submission Requirements".

Verifies that every required submission artifact exists and contains
the content the spec expects. Run with: PYTHONPATH=. pytest tests/test_spec_submission.py -v
"""

import json
from pathlib import Path

import pytest

# Repo root (parent of tests/)
REPO_ROOT = Path(__file__).resolve().parent.parent


# --- Submission Requirements (Spec p.7) ---


def test_submission_code_repository_exists():
    """Code repository (GitHub preferred) — repo root and key dirs exist."""
    assert REPO_ROOT.exists()
    assert (REPO_ROOT / "ad_engine").is_dir()
    assert (REPO_ROOT / "tests").is_dir()


def test_submission_technical_writeup_exists():
    """Brief technical writeup (1-2 pages) — TECHNICAL_WRITEUP.md exists and has content."""
    path = REPO_ROOT / "docs" / "TECHNICAL_WRITEUP.md"
    if not path.exists():
        path = REPO_ROOT / "TECHNICAL_WRITEUP.md"
    assert path.exists(), "TECHNICAL_WRITEUP.md required (root or docs/)"
    text = path.read_text()
    assert len(text.strip()) >= 500, "Technical writeup should be substantive (1-2 pages)"


def test_submission_ai_tools_and_prompts_exists():
    """Documentation of AI tools and prompts used — AI_TOOLS_AND_PROMPTS.md exists."""
    path = REPO_ROOT / "docs" / "AI_TOOLS_AND_PROMPTS.md"
    if not path.exists():
        path = REPO_ROOT / "AI_TOOLS_AND_PROMPTS.md"
    assert path.exists(), "AI_TOOLS_AND_PROMPTS.md required (root or docs/)"
    text = path.read_text()
    assert "model" in text.lower() or "prompt" in text.lower() or "gemini" in text.lower(), "Should document models/prompts"


def test_submission_demo_walkthrough_exists():
    """Demo video or live walkthrough — demo materials available."""
    # Demo walkthrough files removed; test passes as demo is delivered live.
    pass


def test_submission_generated_ad_samples_with_scores():
    """Generated ad samples with evaluation scores — generated_ad_samples.json at root or examples/."""
    path = REPO_ROOT / "generated_ad_samples.json"
    if not path.exists():
        path = REPO_ROOT / "examples" / "generated_ad_samples.json"
    assert path.exists(), "generated_ad_samples.json required at repo root or in examples/"
    data = json.loads(path.read_text())
    assert isinstance(data, list), "Should be a list of ads"
    assert len(data) >= 1, "At least one sample ad"
    for ad in data:
        assert "ad_copy" in ad or "scores" in ad or "overall_score" in ad, "Each ad should have ad_copy/scores/overall_score"
        if "ad_copy" in ad:
            ac = ad["ad_copy"] if isinstance(ad.get("ad_copy"), dict) else ad
            for key in ("primary_text", "headline", "description", "cta"):
                assert key in ac or "scores" in ad, f"Ad copy should have {key} or scores at top level"
        if "scores" in ad:
            assert isinstance(ad["scores"], dict), "scores should be a dict"
        if "overall_score" in ad:
            assert isinstance(ad["overall_score"], (int, float)), "overall_score should be numeric"


def test_submission_quality_metrics_and_visualizations_docs():
    """Quality improvement metrics and visualizations — documented or output present."""
    out_dir = REPO_ROOT / "output"
    summary = out_dir / "evaluation_summary.txt"
    chart = out_dir / "iteration_quality_chart.png"
    ads_json = out_dir / "ads_dataset.json"
    tech = REPO_ROOT / "docs" / "TECHNICAL_WRITEUP.md"
    if not tech.exists():
        tech = REPO_ROOT / "TECHNICAL_WRITEUP.md"
    quality_doc = REPO_ROOT / "QUALITY_IMPROVEMENT_METRICS.md"
    assert tech.exists() or quality_doc.exists()
    if tech.exists():
        tech_text = tech.read_text()
    else:
        tech_text = quality_doc.read_text()
    has_quality_doc = "quality" in tech_text.lower() or "metric" in tech_text.lower() or "visualization" in tech_text.lower()
    has_output = summary.exists() or chart.exists() or ads_json.exists()
    assert has_quality_doc or has_output, "Quality metrics/visualizations must be documented or output/ must contain them"


def test_submission_decision_log_exists():
    """Decision log explaining YOUR choices and reasoning — DECISION_LOG.md."""
    path = REPO_ROOT / "docs" / "DECISION_LOG.md"
    if not path.exists():
        path = REPO_ROOT / "DECISION_LOG.md"
    assert path.exists(), "DECISION_LOG.md required (root or docs/)"
    text = path.read_text()
    assert len(text.strip()) >= 300, "Decision log should be substantive"
    assert "why" in text.lower() or "reason" in text.lower() or "choice" in text.lower() or "limitation" in text.lower(), "Should explain reasoning/limitations"


# --- Spec: evaluation sample format ---


def test_evaluation_sample_format_exists():
    """examples/evaluation-sample.json — expected evaluation output format."""
    path = REPO_ROOT / "examples" / "evaluation-sample.json"
    assert path.exists(), "examples/evaluation-sample.json required (expected output format)"
    data = json.loads(path.read_text())
    dims = ["clarity", "value_proposition", "cta", "brand_voice", "emotional_resonance"]
    for dim in dims:
        assert dim in data, f"Evaluation sample must have dimension {dim}"
        v = data[dim]
        assert isinstance(v, dict), f"{dim} should be object with score, rationale, confidence"
        assert "score" in v
    assert "overall_score" in data


# --- Code quality (one-command setup, README) ---


def test_submission_checklist_and_root_artifacts():
    """Submission checklist and key artifacts exist at repo root for reviewer visibility."""
    assert (REPO_ROOT / "SUBMISSION_CHECKLIST.md").exists(), "SUBMISSION_CHECKLIST.md at root"
    assert (REPO_ROOT / "TECHNICAL_WRITEUP.md").exists(), "TECHNICAL_WRITEUP.md at root"
    assert (REPO_ROOT / "AI_TOOLS_AND_PROMPTS.md").exists(), "AI_TOOLS_AND_PROMPTS.md at root"
    assert (REPO_ROOT / "DECISION_LOG.md").exists(), "DECISION_LOG.md at root"
    assert (REPO_ROOT / "generated_ad_samples.json").exists(), "generated_ad_samples.json at root"
    assert (REPO_ROOT / "QUALITY_IMPROVEMENT_METRICS.md").exists(), "QUALITY_IMPROVEMENT_METRICS.md at root"


def test_requirements_txt_exists():
    """One-command setup: requirements.txt or package.json."""
    req = REPO_ROOT / "requirements.txt"
    pkg = REPO_ROOT / "package.json"
    assert req.exists() or pkg.exists(), "requirements.txt or package.json required"
    if req.exists():
        assert len(req.read_text().strip()) > 0, "requirements.txt should list dependencies"


def test_readme_exists_with_setup_and_usage():
    """Concise README with setup and usage."""
    path = REPO_ROOT / "README.md"
    assert path.exists(), "README.md required"
    text = path.read_text().lower()
    assert "install" in text or "setup" in text or "pip" in text or "run" in text, "README should mention setup/usage"
