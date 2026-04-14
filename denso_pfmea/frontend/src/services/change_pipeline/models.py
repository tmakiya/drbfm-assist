from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import pandas as pd

from src.common.bop import ChangeRecord
from src.services.pfmea_context import PfmeaContext


class ComparisonMode(str, Enum):
    SINGLE_VARIANT = "single_variant"
    ALL_VARIANTS = "all_variants"


@dataclass(frozen=True)
class ComparisonStats:
    detected_total: int
    suppressed: int
    retained_total: int
    actionable: int

    def to_dict(self) -> dict[str, int]:
        return {
            "detected_total": self.detected_total,
            "suppressed": self.suppressed,
            "retained_total": self.retained_total,
            "actionable": self.actionable,
        }


class ChangePipelineError(RuntimeError):
    """差分解析で想定外の致命エラーが発生した場合に送出される。"""


@dataclass(frozen=True)
class ChangeAnalysisResult:
    comparison_label: str
    actionable_changes: tuple[ChangeRecord, ...]
    change_report: pd.DataFrame
    pfmea_context: dict[str, PfmeaContext]
    has_label_mismatch: bool
    comparison_mode: ComparisonMode
    comparison_stats: ComparisonStats

    @property
    def has_changes(self) -> bool:
        return bool(self.actionable_changes)


class ProgressReporter(Protocol):
    def __call__(self, *, completed: int, total: int, label: str) -> None:
        """進捗レポート用コールバック。"""


__all__ = [
    "ChangeAnalysisResult",
    "ChangePipelineError",
    "ComparisonMode",
    "ComparisonStats",
    "ProgressReporter",
]
