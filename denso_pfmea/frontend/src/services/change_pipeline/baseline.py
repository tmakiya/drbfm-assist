from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from src.common.bop import ChangeRecord
from src.common.bop.diff import normalize_part_value


def collect_baseline_values(
    parts: pd.DataFrame,
    canonical_to_source_key: Mapping[str, str | None],
) -> Mapping[str, set[str]]:
    """Build a lookup of canonical column → historical part numbers across variants."""
    baseline: dict[str, set[str]] = {}
    if parts.empty:
        return baseline
    source_keys = {
        canonical: key for canonical, key in canonical_to_source_key.items() if key
    }
    if not source_keys:
        return baseline

    for canonical_key in source_keys:
        baseline[canonical_key] = set()

    for _, row in parts.iterrows():
        for canonical_key, source_key in source_keys.items():
            if source_key not in row:
                continue
            value = row.get(source_key, "")
            normalized = _normalize_candidate(value)
            if normalized:
                baseline[canonical_key].add(normalized)
    return baseline


def should_suppress_change(
    change: ChangeRecord,
    baseline_values: Mapping[str, set[str]],
) -> bool:
    """Return True when the change is already present in any baseline variant."""
    if change.change_type == "削除":
        return False
    normalized_new = _normalize_candidate(change.new_value)
    if not normalized_new:
        return False
    normalized_old = _normalize_candidate(change.original_value)
    if normalized_new == normalized_old:
        return False
    candidates = baseline_values.get(change.column_key)
    if not candidates:
        return False
    return normalized_new in candidates


def _normalize_candidate(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        if isinstance(value, float) and pd.isna(value):
            return ""
        text = str(value)
    return normalize_part_value(text)


__all__ = ["collect_baseline_values", "should_suppress_change"]
