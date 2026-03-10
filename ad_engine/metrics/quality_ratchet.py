"""v3: Quality ratchet — standards only go UP."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def load_run_history(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def best_avg_score_so_far(run_history_path: Path) -> float:
    """Return the highest avg_score across all runs (quality ratchet: bar only goes up)."""
    runs = load_run_history(run_history_path)
    if not runs:
        return 0.0
    return max(float(r.get("avg_score", 0)) for r in runs)


def quality_floor_for_run(
    run_history_path: Path,
    default_floor: float = 7.0,
) -> float:
    """
    Return the current quality floor for accepting runs: max(default_floor, best_avg_so_far - tolerance).
    We allow the floor to be at least default_floor (7.0); once we've seen better runs, we don't lower the bar.
    """
    best = best_avg_score_so_far(run_history_path)
    return max(default_floor, best)


def apply_ratchet_to_summary(
    run_history_path: Path,
    summary_lines: List[str],
    default_threshold: float = 7.0,
) -> List[str]:
    """
    Append quality ratchet line(s) to evaluation summary text.
    """
    best = best_avg_score_so_far(run_history_path)
    floor = quality_floor_for_run(run_history_path, default_floor=default_threshold)
    ratchet_note = (
        f"\nQuality ratchet (v3): Best avg score so far = {best:.2f}. "
        f"Current floor = {floor:.2f} (standards only go UP).\n"
    )
    return summary_lines + [ratchet_note]
