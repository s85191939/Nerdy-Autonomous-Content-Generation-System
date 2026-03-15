"""Cross-run learning: analyze top ads from past runs and extract reusable patterns."""

from ad_engine.learning.insights import (
    analyze_learnings,
    gather_top_ads,
    load_learned_insights,
    save_learned_insights,
)

__all__ = ["gather_top_ads", "analyze_learnings", "save_learned_insights", "load_learned_insights"]
