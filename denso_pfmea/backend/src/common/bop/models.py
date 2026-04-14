from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class PartColumn:
    key: str
    col_idx: int
    block: str
    station: str
    part_label: str


@dataclass
class ChangeRecord:
    variant_id: str
    block: str
    station: str
    part_label: str
    column_key: str
    original_value: str
    new_value: str
    change_type: str  # 追加 / 変更 / 削除 / 名称不一致 / 数量追加 / 数量減少 / 品番変更
    keywords: list[str]
    change_id: str
    original_part_label: str | None = None
    updated_part_label: str | None = None
    is_label_mismatch: bool = False
    shape_feature: str | None = None
    preceding_part_label: str | None = None
    following_part_label: str | None = None
    preceding_original_value: str | None = None
    preceding_new_value: str | None = None
    following_original_value: str | None = None
    following_new_value: str | None = None
    variant_metadata: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class BopDataset:
    metadata: pd.DataFrame
    parts: pd.DataFrame
    column_catalog: pd.DataFrame
    annotations: dict[str, str] = field(default_factory=dict)

    def as_tuple(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return self.metadata, self.parts, self.column_catalog


__all__ = ["BopDataset", "ChangeRecord", "PartColumn"]
