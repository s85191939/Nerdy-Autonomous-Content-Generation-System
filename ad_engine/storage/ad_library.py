"""In-memory ad library and evaluation log (persist to JSON for simplicity)."""

import json
from pathlib import Path
from typing import Any, Union

from ad_engine.config import DIMENSION_NAMES


class AdLibrary:
    """Store accepted ads and evaluation logs. Persists to JSON files."""

    def __init__(self, base_path: Union[str, Path] = "output"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._ads: list[dict[str, Any]] = []
        self._eval_logs: list[dict[str, Any]] = []

    def add(
        self,
        ad_id: str,
        brief: dict,
        ad_copy: dict,
        scores: dict,
        overall_score: float,
        iteration_count: int,
        generation_cost: float = 0.0,
    ) -> None:
        record = {
            "id": ad_id,
            "brief": brief,
            "ad_copy": ad_copy,
            "scores": scores,
            "overall_score": overall_score,
            "iteration_count": iteration_count,
            "generation_cost": generation_cost,
        }
        self._ads.append(record)

    def log_evaluation(
        self,
        ad_id: str,
        dimension: str,
        score: float,
        rationale: str,
        model_version: str = "",
    ) -> None:
        self._eval_logs.append({
            "ad_id": ad_id,
            "dimension": dimension,
            "score": score,
            "rationale": rationale,
            "model_version": model_version,
        })

    def list_ads(self) -> list:
        return list(self._ads)

    def save(self, prefix: str = "ad_library") -> None:
        ads_file = self.base_path / f"{prefix}_ads.json"
        logs_file = self.base_path / f"{prefix}_eval_logs.json"
        with open(ads_file, "w") as f:
            json.dump(self._ads, f, indent=2)
        with open(logs_file, "w") as f:
            json.dump(self._eval_logs, f, indent=2)

    def load(self, prefix: str = "ad_library") -> None:
        ads_file = self.base_path / f"{prefix}_ads.json"
        logs_file = self.base_path / f"{prefix}_eval_logs.json"
        if ads_file.exists():
            with open(ads_file) as f:
                self._ads = json.load(f)
        if logs_file.exists():
            with open(logs_file) as f:
                self._eval_logs = json.load(f)

    def __len__(self) -> int:
        return len(self._ads)
