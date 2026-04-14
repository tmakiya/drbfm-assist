"""Helpers for applying PFMEA mapping results to DataFrames."""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from .function_mapper import (
    FunctionMappingError,
    FunctionMappingRecord,
    deserialize_records,
)


def apply_records_to_dataframe(
    df: pd.DataFrame,
    requirement_indices: Sequence[int],
    records: Sequence[FunctionMappingRecord],
) -> None:
    """Apply mapping records to dataframe inplace."""
    if "mapped_function" not in df.columns:
        df["mapped_function"] = ""
    if "mapped_assurance" not in df.columns:
        df["mapped_assurance"] = ""
    if "mapping_reason" not in df.columns:
        df["mapping_reason"] = ""

    for record in records:
        offset = record.requirement_index - 1
        if offset < 0 or offset >= len(requirement_indices):
            raise FunctionMappingError("マッピングの要求事項インデックスが範囲外です。")

        row_idx = requirement_indices[offset]
        df.at[row_idx, "mapped_function"] = record.function
        df.at[row_idx, "mapped_assurance"] = record.assurance
        df.at[row_idx, "mapping_reason"] = record.reason


def apply_cached_mapping(
    cached_entry: Mapping[str, object],
    dataframe: pd.DataFrame,
    requirement_indices: Sequence[int],
) -> tuple[tuple[FunctionMappingRecord, ...], str, tuple[str, ...]]:
    """Deserialize cached payload and apply it to the dataframe."""
    records = deserialize_records(cached_entry.get("records", []))  # type: ignore[arg-type]
    raw_text = str(cached_entry.get("raw_text", ""))
    cached_errors = tuple(str(item) for item in cached_entry.get("errors", []))  # type: ignore[attr-defined]

    if len(records) != len(requirement_indices):
        raise FunctionMappingError(
            f"マッピング結果の行数が要求事項数と一致しません（{len(records)} != {len(requirement_indices)}）。"
        )

    apply_records_to_dataframe(dataframe, list(requirement_indices), records)
    return records, raw_text, cached_errors


__all__ = ["apply_cached_mapping", "apply_records_to_dataframe"]
