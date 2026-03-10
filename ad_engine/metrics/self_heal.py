"""v3: Self-healing feedback loops — detect quality drops, diagnose, auto-fix."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Drop threshold: if current run avg is this much below previous run, trigger healing
QUALITY_DROP_THRESHOLD = 0.5


def load_run_history(path: Path) -> List[Dict[str, Any]]:
    """Load run_history.json; return list of runs or empty."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def detect_quality_drop(
    current_avg_score: float,
    run_history_path: Path,
    min_runs_to_compare: int = 1,
) -> Tuple[bool, str]:
    """
    Compare current run avg to previous run(s). Return (True, message) if drop detected.
    """
    runs = load_run_history(run_history_path)
    if len(runs) < min_runs_to_compare:
        return False, ""
    # Compare to most recent run (which may be the one we're about to append)
    prev = runs[-1]
    prev_avg = prev.get("avg_score")
    if prev_avg is None:
        return False, ""
    drop = prev_avg - current_avg_score
    if drop >= QUALITY_DROP_THRESHOLD:
        return True, (
            f"Quality drop detected: current avg {current_avg_score:.2f} vs previous {prev_avg:.2f} (Δ = -{drop:.2f}). "
            "Suggest: recalibrate evaluator on reference ads, or re-iterate this run."
        )
    return False, ""


def suggest_auto_fix(
    run_history_path: Path,
    output_dir: Path,
    current_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    After a quality drop, suggest an auto-fix action.
    Returns dict: { "action": "recalibrate" | "iterate_campaign" | "none", "message": str, "run_id": str | None }.
    """
    runs = load_run_history(run_history_path)
    if not runs:
        return {"action": "none", "message": "No prior runs to compare.", "run_id": None}
    latest = runs[-1]
    latest_avg = latest.get("avg_score", 0)
    run_id = current_run_id or latest.get("run_id")
    # Prefer suggesting iterate_campaign on the latest run to try to improve scores
    if run_id:
        return {
            "action": "iterate_campaign",
            "message": f"Run {run_id} had avg {latest_avg:.2f}. Re-iterate with: python -m ad_engine.cli iterate --run-id <run_id> (or run calibrate_evaluator.py first).",
            "run_id": run_id,
        }
    return {"action": "recalibrate", "message": "Run calibrate_evaluator.py on reference ads, then re-run pipeline.", "run_id": None}


def run_self_heal_checks(
    current_avg_score: float,
    output_dir: Path,
    run_id: str,
) -> None:
    """
    Called after appending a run to run_history. If quality dropped vs previous run,
    write output/self_heal_suggestion.txt with diagnosis and suggested fix.
    """
    out_dir = Path(output_dir)
    history_path = out_dir / "run_history.json"
    dropped, msg = detect_quality_drop(current_avg_score, history_path, min_runs_to_compare=2)
    if not dropped:
        return
    logger.warning("Self-heal: %s", msg)
    fix = suggest_auto_fix(history_path, out_dir, current_run_id=run_id)
    suggestion_path = out_dir / "self_heal_suggestion.txt"
    try:
        suggestion_path.write_text(
            "Self-healing (v3): Quality drop detected.\n"
            "==============================\n\n"
            f"{msg}\n\n"
            f"Suggested action: {fix['action']}\n"
            f"{fix['message']}\n"
        )
    except Exception as e:
        logger.warning("Could not write self_heal_suggestion.txt: %s", e)
