from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any, NotRequired, TypedDict


class StageBlueprint(TypedDict):
    id: str
    label_template: NotRequired[str]
    weight: NotRequired[int]


class StageEntry(TypedDict):
    id: str
    label: str
    weight: int
    state: str
    message: str


class DatasetStageTracker:
    """Thread-safe helper to report dataset loading progress."""

    def __init__(
        self,
        *,
        source_label: str,
        target_label: str,
        pfmea_label: str,
        stage_blueprints: Sequence[StageBlueprint],
    ) -> None:
        self._lock = threading.Lock()
        labels = {
            "source_label": source_label,
            "target_label": target_label,
            "pfmea_label": pfmea_label,
        }
        self._stages: list[StageEntry] = []
        self._stage_map: dict[str, StageEntry] = {}
        self._error_stage_id: str | None = None

        for blueprint in stage_blueprints:
            stage_id = blueprint["id"]
            label_template = blueprint.get("label_template", stage_id)
            label = label_template.format(**labels)
            entry: StageEntry = {
                "id": stage_id,
                "label": label,
                "weight": int(blueprint.get("weight", 0)),
                "state": "pending",
                "message": "",
            }
            self._stages.append(entry)
            self._stage_map[stage_id] = entry

    def _set_state(
        self,
        stage_id: str,
        state: str,
        *,
        message: str | None = None,
    ) -> None:
        with self._lock:
            stage = self._stage_map.get(stage_id)
            if stage is None:
                return
            stage["state"] = state
            if message is not None:
                stage["message"] = message
            if state == "error":
                self._error_stage_id = stage_id

    def mark_running(self, stage_id: str, message: str | None = None) -> None:
        self._set_state(stage_id, "running", message=message)

    def mark_complete(self, stage_id: str, message: str | None = None) -> None:
        self._set_state(stage_id, "complete", message=message)

    def mark_error(self, stage_id: str, message: str | None = None) -> None:
        self._set_state(stage_id, "error", message=message)

    def stage_label(self, stage_id: str) -> str:
        stage = self._stage_map.get(stage_id)
        if stage is None:
            return stage_id
        return stage["label"]

    def has_error(self) -> bool:
        with self._lock:
            return self._error_stage_id is not None

    def _progress_value_locked(self) -> int:
        total_weight = sum(stage["weight"] for stage in self._stages) or 100
        completed = sum(
            stage["weight"] for stage in self._stages if stage["state"] == "complete"
        )
        running = sum(
            stage["weight"] for stage in self._stages if stage["state"] == "running"
        )
        progress = completed + int(round(running * 0.5))
        progress = min(progress, total_weight)
        return int(round((progress / total_weight) * 100))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            stages = [
                {
                    "id": stage["id"],
                    "label": stage["label"],
                    "state": stage["state"],
                    "message": stage["message"],
                }
                for stage in self._stages
            ]
            running_stage = next(
                (stage for stage in self._stages if stage["state"] == "running"),
                None,
            )
            pending_stage = next(
                (stage for stage in self._stages if stage["state"] == "pending"),
                None,
            )
            active_stage = running_stage or pending_stage
            active_stage_id: str | None = None
            active_stage_label: str | None = None
            if active_stage is not None:
                active_stage_id = active_stage["id"]
                active_stage_label = active_stage["label"]
            progress_value = self._progress_value_locked()
            error_stage_id = self._error_stage_id
            return {
                "progress": progress_value,
                "stages": stages,
                "active_stage_id": active_stage_id,
                "active_stage_label": active_stage_label,
                "error_stage_id": error_stage_id,
                "error_stage_label": self.stage_label(error_stage_id)
                if error_stage_id
                else None,
            }


__all__ = ["DatasetStageTracker", "StageBlueprint"]
