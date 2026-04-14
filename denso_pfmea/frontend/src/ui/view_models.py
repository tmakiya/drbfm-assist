from __future__ import annotations

import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import pandas as pd

from src.common.bop import BopDataset
from src.ui.excel_styling import apply_excel_styling
from src.ui.shared_constants import PFMEA_BLOCKS


def _shorten(text: str, width: int = 60) -> str:
    if not text:
        return ""
    return textwrap.shorten(text, width=width, placeholder="…")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _display_value(value: str) -> str:
    return value if value else "（なし）"


def _format_transition(original: str, updated: str) -> str:
    before = _display_value(original)
    after = _display_value(updated)
    if before == after:
        return after
    return f"{before}→{after}"


def _describe_change_reason(
    change_type: str,
    original_part_label: str,
    updated_part_label: str,
    original_value: str,
    new_value: str,
    data_quality_warning: str,
) -> str:
    base_type = change_type or "不明"
    before_label = original_part_label or "（未設定）"
    after_label = updated_part_label or "（未設定）"
    before_value = _display_value(original_value)
    after_value = _display_value(new_value)

    reason: str
    if base_type == "品番変更":
        reason = f"{after_label}の品番が {before_value} → {after_value} に変化"
    elif base_type == "追加":
        reason = f"流用元が未設定で新品番 {after_value} が登録されたため追加"
    elif base_type == "削除":
        reason = f"変更後が未設定で旧品番 {before_value} の行が削除されたと判断"
    elif base_type == "名称不一致":
        reason = f"品番は一致 ({before_value}) だが部品名が {before_label} → {after_label} へ変化"
    elif base_type == "数量追加":
        reason = f"数量が {before_value} → {after_value} と増加"
    elif base_type == "数量減少":
        reason = f"数量が {before_value} → {after_value} と減少"
    elif base_type == "変更":
        details = []
        if original_part_label != updated_part_label:
            details.append(f"部品名 {before_label} → {after_label}")
        if original_value != new_value:
            details.append(f"品番 {before_value} → {after_value}")
        if not details:
            details.append(f"旧値 {before_value} / 新値 {after_value}")
        reason = f"{base_type}: " + "、".join(details)
    else:
        reason = f"{base_type}: 旧値 {before_value} / 新値 {after_value}"

    if data_quality_warning:
        reason = f"{reason} / 警告: {data_quality_warning}"
    return reason


@dataclass(frozen=True)
class VariantOverviewViewModel:
    source_variants: tuple[str, ...]
    target_variants: tuple[str, ...]
    source_count: int
    target_count: int
    added_variants: tuple[str, ...]
    removed_variants: tuple[str, ...]
    multiple_target_rows: bool
    primary_target_variant: str
    source_metadata: pd.DataFrame = field(repr=False)
    target_metadata: pd.DataFrame = field(repr=False)

    @classmethod
    def from_datasets(
        cls, source: BopDataset, target: BopDataset
    ) -> VariantOverviewViewModel:
        source_variants = tuple(source.parts.index.tolist())
        target_variants = tuple(target.parts.index.tolist())
        added = tuple(
            variant for variant in target_variants if variant not in source_variants
        )
        removed = tuple(
            variant for variant in source_variants if variant not in target_variants
        )
        primary_target_variant = target_variants[0] if target_variants else ""
        return cls(
            source_variants=source_variants,
            target_variants=target_variants,
            source_count=len(source_variants),
            target_count=len(target_variants),
            added_variants=added,
            removed_variants=removed,
            multiple_target_rows=len(target_variants) > 1,
            primary_target_variant=primary_target_variant,
            source_metadata=source.metadata,
            target_metadata=target.metadata,
        )


@dataclass(frozen=True)
class ChangeImpactRow:
    change_id: str
    block: str
    station: str
    part_label: str
    shape_feature: str
    change_type: str
    part_number: str
    difference_reason: str

    @classmethod
    def from_series(cls, row: pd.Series) -> ChangeImpactRow:
        source_part_label = _safe_str(row.get("対象部品（流用元）", ""))
        target_part_label = _safe_str(row.get("対象部品（変更後）", ""))
        base_part_label = _safe_str(row.get("対象部品", ""))

        has_source = bool(source_part_label)
        has_target = bool(target_part_label)

        if has_source or has_target:
            display_old = source_part_label or "（なし）"
            display_new = target_part_label or "（なし）"
            if display_old != display_new:
                part_label_display = f"{display_old}→{display_new}"
            else:
                part_label_display = target_part_label or source_part_label
        else:
            part_label_display = base_part_label

        if not part_label_display:
            part_label_display = "（未設定）"

        original_value = _safe_str(row.get("旧品番", ""))
        new_value = _safe_str(row.get("新品番", ""))
        change_type = _safe_str(row.get("変更種別", ""))
        data_quality_warning = _safe_str(row.get("データ品質警告", ""))
        part_number_display = _format_transition(original_value, new_value)
        difference_reason = _describe_change_reason(
            change_type,
            source_part_label,
            target_part_label,
            original_value,
            new_value,
            data_quality_warning,
        )

        return cls(
            change_id=str(row.get("変更ID", "")),
            block=str(row.get("ブロック", "")),
            station=str(row.get("ステーション", "")),
            part_label=part_label_display,
            shape_feature=str(row.get("形状の特長", "")),
            change_type=change_type,
            part_number=part_number_display,
            difference_reason=difference_reason,
        )


@dataclass
class ChangeImpactTableViewModel:
    rows: tuple[ChangeImpactRow, ...]
    change_types: tuple[str, ...]
    _base_df: pd.DataFrame = field(repr=False)
    _display_columns: tuple[str, ...] = field(repr=False)

    @classmethod
    def from_sources(
        cls,
        change_report: pd.DataFrame,
    ) -> ChangeImpactTableViewModel:
        ordered_report = change_report.copy()
        ordered_report["_row_order"] = range(len(ordered_report))

        if "ブロック" in ordered_report.columns:
            block_priority = {block: idx for idx, block in enumerate(PFMEA_BLOCKS)}
            ordered_report["_block_order"] = (
                ordered_report["ブロック"]
                .map(block_priority)
                .fillna(len(block_priority))
            )
            ordered_report = ordered_report.sort_values(
                ["_block_order", "_row_order"], kind="mergesort"
            )
        else:
            ordered_report = ordered_report.sort_values(
                ["_row_order"], kind="mergesort"
            )

        rows = []
        enriched_records = []
        has_shape_feature = False
        for _, row in ordered_report.iterrows():
            row_model = ChangeImpactRow.from_series(row)
            rows.append(row_model)
            if row_model.shape_feature:
                has_shape_feature = True
            enriched_records.append(
                {
                    "変更ID": row_model.change_id,
                    "ブロック": row_model.block,
                    "ステーション": row_model.station,
                    "対象部品": row_model.part_label,
                    "形状の特長": row_model.shape_feature,
                    "変更種別": row_model.change_type,
                    "品番": row_model.part_number,
                    "差異理由": row_model.difference_reason,
                }
            )

        # ベースDataFrame（全カラム保持）
        base_df = pd.DataFrame(enriched_records)

        # 表示用のカラムリストを決定
        all_columns = list(base_df.columns) if not base_df.empty else []
        display_columns = [c for c in all_columns if c != "変更ID"]
        if not has_shape_feature and "形状の特長" in display_columns:
            display_columns = [c for c in display_columns if c != "形状の特長"]

        change_types = tuple(
            sorted({row.change_type for row in rows if row.change_type})
        )

        return cls(
            rows=tuple(rows),
            change_types=change_types,
            _base_df=base_df,
            _display_columns=tuple(display_columns),
        )

    @property
    def display_df(self) -> pd.DataFrame:
        if self._base_df.empty:
            return self._base_df.copy()
        return self._base_df[list(self._display_columns)].copy()

    def filter(
        self,
        selected_change_types: Sequence[str],
        selected_keywords: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        df = self.display_df
        if not df.empty and selected_change_types:
            df = df[df["変更種別"].isin(selected_change_types)]
        return df

    def csv_bytes(self) -> bytes:
        """CSV遅延生成（呼び出し時のみ）"""
        download_df = self._base_df
        if "変更ID" in download_df.columns:
            download_df = download_df.drop(columns=["変更ID"])
        return download_df.to_csv(index=False).encode("utf-8-sig")

    def xlsx_bytes(self) -> bytes:
        """Export as Excel (.xlsx) format with styling."""
        download_df = self._base_df
        if "変更ID" in download_df.columns:
            download_df = download_df.drop(columns=["変更ID"])
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            download_df.to_excel(writer, index=False, sheet_name="変更レポート")
            apply_excel_styling(writer.book["変更レポート"])
        return buffer.getvalue()
