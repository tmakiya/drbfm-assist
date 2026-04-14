"""Validation utilities for parsed datasets."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from .bop import BopDataset
from .pfmea import PfmeaDataset

Severity = Literal["warning", "error"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    message: str


def _ensure_columns_present(
    df: pd.DataFrame, columns: Iterable[str], label: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    missing = [col for col in columns if col not in df.columns]
    if missing:
        issues.append(
            ValidationIssue(
                severity="warning",
                message=f"{label} に推奨列 {', '.join(missing)} が見つかりません。ファイル構造を確認してください。",
            )
        )
    return issues


def validate_bop_dataset(dataset: BopDataset) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if dataset.parts.empty:
        issues.append(
            ValidationIssue(
                severity="error", message="編成表に有効なバリエーション行がありません。"
            )
        )
    if dataset.column_catalog.empty:
        issues.append(
            ValidationIssue(
                severity="error",
                message="部品カラムを認識できませんでした。ヘッダ構造を確認してください。",
            )
        )
    issues.extend(
        _ensure_columns_present(
            dataset.metadata, ["流動ライン", "車種", "ユニット"], "編成表メタデータ"
        )
    )
    if dataset.parts.index.duplicated().any():
        issues.append(
            ValidationIssue(
                severity="warning",
                message="編成表の行ラベルが重複しています。バリエーション識別子を確認してください。",
            )
        )
    return issues


def validate_pfmea_bundle(
    dataset: PfmeaDataset, expected_blocks: Iterable[str]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_columns = [
        "process_name",
        "failure_mode",
        "severity",
        "occurrence",
        "detection",
        "rpn",
    ]

    def _normalized(series: pd.Series) -> pd.Series:
        return series.fillna("").astype(str).map(str.strip)

    def _summarize_indexes(indexes: list[int], *, limit: int = 5) -> str:
        if not indexes:
            return ""
        head = indexes[:limit]
        suffix = "" if len(indexes) <= limit else " 他"
        return ",".join(str(idx) for idx in head) + suffix

    for block in expected_blocks:
        if block not in dataset.by_block:
            issues.append(
                ValidationIssue(
                    severity="error", message=f"PFMEA ({block}) が未提供です。"
                )
            )
            continue
        df = dataset.by_block[block]
        if df.empty:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"PFMEA ({block}) に有効な行がありません。",
                )
            )
            continue
        issues.extend(_ensure_columns_present(df, required_columns, f"PFMEA ({block})"))

        excel_rows = df.get("excel_row")

        def _coerce_row_number(value: Any, *, offset: int = 0) -> int | None:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                if pd.isna(value):
                    return None
                return int(value) + offset
            text = str(value).strip()
            if not text:
                return None
            try:
                numeric = int(float(text))
            except (ValueError, TypeError):
                return None
            return numeric + offset

        def _resolve_row_numbers(
            indexes: list[Any], excel_rows_series: Any = excel_rows
        ) -> list[Any]:
            resolved: list[Any] = []
            for idx in indexes:
                row_number = None
                if excel_rows_series is not None:
                    try:
                        candidate = excel_rows_series.loc[idx]
                    except KeyError:
                        candidate = None
                    row_number = _coerce_row_number(candidate)
                if row_number is None:
                    row_number = _coerce_row_number(idx, offset=1)
                resolved.append(row_number if row_number is not None else idx)
            return resolved

        requirement_col = df.get("requirement")
        if requirement_col is not None:
            normalized = _normalized(requirement_col)
            empty_indexes = [
                idx for idx, value in zip(df.index, normalized) if not value
            ]
            empty_rows = _resolve_row_numbers(empty_indexes)
            if empty_rows:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"PFMEA ({block}) の要求事項に空欄があります（行: {_summarize_indexes(empty_rows)}）。これらの行はスキップされます。",
                    )
                )
            duplicates = normalized[normalized != ""].duplicated(keep=False)
            if duplicates.any():
                dup_indexes = [idx for idx, flag in zip(df.index, duplicates) if flag]
                dup_rows = _resolve_row_numbers(dup_indexes)
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"PFMEA ({block}) の要求事項が重複しています（行: {_summarize_indexes(dup_rows)}）。自動的に識別子が付与されます。",
                    )
                )

        assurance_col = df.get("manufacturing_assurance")
        if assurance_col is not None:
            normalized = _normalized(assurance_col)
            empty_indexes = [
                idx for idx, value in zip(df.index, normalized) if not value
            ]
            empty_rows = _resolve_row_numbers(empty_indexes)
            if empty_rows:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"PFMEA ({block}) の製造保証項目に空欄があります（行: {_summarize_indexes(empty_rows)}）。",
                    )
                )
            duplicates = normalized[normalized != ""].duplicated(keep=False)
            if duplicates.any():
                dup_indexes = [idx for idx, flag in zip(df.index, duplicates) if flag]
                dup_rows = _resolve_row_numbers(dup_indexes)
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"PFMEA ({block}) の製造保証項目が重複しています（行: {_summarize_indexes(dup_rows)}）。適宜区別できる表現にしてください。",
                    )
                )

    return issues
