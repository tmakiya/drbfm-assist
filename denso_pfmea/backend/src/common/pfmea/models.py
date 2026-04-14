from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ShapeText:
    row: int
    col: int
    text: str


@dataclass
class ProcessSummary:
    """工程単位のテキストボックス/備考情報。"""

    process_name: str
    anchor_row: int
    raw_text: str
    functions: tuple[str, ...] = field(default_factory=tuple)
    requirements: tuple[str, ...] = field(default_factory=tuple)
    extra_sections: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass
class PfmeaEntry:
    excel_row: int
    process_name: str
    process_detail: str
    process_functions: tuple[str, ...]
    process_requirements: tuple[str, ...]
    requirement: str
    failure_mode: str
    effect: str
    severity: int
    priority_designation: str
    cause: str
    prevention: str
    occurrence: int
    detection_control: str
    detection: int
    rpn: int
    recommended_action: str
    process_sheet_reflection: str
    responsible_owner: str


@dataclass
class RatingScales:
    severity: dict[int, str]
    occurrence: dict[int, str]
    detection: dict[int, str]


@dataclass
class PfmeaDataset:
    by_block: dict[str, pd.DataFrame]
    rating_scales: RatingScales
    process_summaries: dict[str, dict[str, ProcessSummary]] = field(
        default_factory=dict
    )


__all__ = [
    "PfmeaDataset",
    "PfmeaEntry",
    "ProcessSummary",
    "RatingScales",
    "ShapeText",
]
