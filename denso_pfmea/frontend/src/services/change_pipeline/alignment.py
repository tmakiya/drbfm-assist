from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from src.common.bop.alignment import compute_column_alignment


def _make_canonical_catalog(
    catalog: pd.DataFrame, mapping: Mapping[str, str | None]
) -> pd.DataFrame:
    if catalog.empty:
        return pd.DataFrame(columns=catalog.columns)
    records: dict[str, pd.Series] = {}
    for canonical, original in mapping.items():
        if original is None or original not in catalog.index:
            continue
        records[canonical] = catalog.loc[original]
    if not records:
        return pd.DataFrame(columns=catalog.columns)
    return pd.DataFrame.from_dict(records, orient="index")


def _canonical_sort_key(
    canonical_key: str,
    source_catalog: pd.DataFrame,
    target_catalog: pd.DataFrame,
) -> tuple[str, str, int, str]:
    if canonical_key in source_catalog.index:
        row = source_catalog.loc[canonical_key]
    elif canonical_key in target_catalog.index:
        row = target_catalog.loc[canonical_key]
    else:
        row = None
    if row is not None:
        block = str(row.get("block", "") or "")
        station = str(row.get("station", "") or "")
        idx_value = row.get("column_index")
        try:
            column_index = int(idx_value) if pd.notna(idx_value) else 9999
        except (TypeError, ValueError):
            column_index = 9999
        return block, station, column_index, canonical_key
    return "", "", 9999, canonical_key


def build_canonical_alignment(
    source_catalog: pd.DataFrame,
    target_catalog: pd.DataFrame,
    target_annotations: Mapping[str, str],
) -> tuple[
    list[str],
    pd.DataFrame,
    pd.DataFrame,
    dict[str, str | None],
    dict[str, str | None],
    dict[str, str],
]:
    rename_map = compute_column_alignment(source_catalog, target_catalog)

    canonical_to_source: dict[str, str | None] = {
        key: key for key in source_catalog.index
    }
    canonical_to_target: dict[str, str | None] = {}

    for target_key in target_catalog.index:
        canonical = rename_map.get(target_key, target_key)
        canonical_to_target.setdefault(canonical, target_key)
        canonical_to_source.setdefault(canonical, None)

    for canonical in list(canonical_to_source.keys()):
        canonical_to_target.setdefault(canonical, None)

    source_canonical_catalog = _make_canonical_catalog(
        source_catalog, canonical_to_source
    )
    target_canonical_catalog = _make_canonical_catalog(
        target_catalog, canonical_to_target
    )

    canonical_keys = sorted(
        set(canonical_to_source.keys()).union(canonical_to_target.keys()),
        key=lambda key: _canonical_sort_key(
            key, source_canonical_catalog, target_canonical_catalog
        ),
    )

    target_annotations_canonical = {
        canonical: target_annotations[original]
        for canonical, original in canonical_to_target.items()
        if original is not None and original in target_annotations
    }

    return (
        canonical_keys,
        source_canonical_catalog,
        target_canonical_catalog,
        canonical_to_source,
        canonical_to_target,
        target_annotations_canonical,
    )


__all__ = ["build_canonical_alignment"]
