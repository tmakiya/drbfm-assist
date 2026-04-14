from __future__ import annotations

import math
import re
from collections.abc import Iterable

import pandas as pd

from src.common import generate_change_id
from src.common.concurrency import parallel_map
from src.common.config import BopConfig
from src.common.text_utils import normalize_text, sanitize

from .alignment import compute_column_alignment
from .constants import ABSENT_MARKERS
from .models import ChangeRecord
from .settings import get_bop_config


def normalize_part_value(value: str) -> str:
    """Normalize part value with NFKC and whitespace handling."""
    cleaned = sanitize(value)
    if cleaned in ABSENT_MARKERS:
        return ""
    # Apply NFKC normalization for full-width/half-width consistency
    return normalize_text(cleaned)


def extract_keywords(part_label: str, config: BopConfig | None = None) -> list[str]:
    conf = config or get_bop_config()
    label = part_label or ""
    found = []
    for category, patterns in conf.keyword_categories.items():
        if any(pattern in label for pattern in patterns):
            found.append(category)
    return found


def _lookup_metadata(column_key: str, catalog: pd.DataFrame) -> pd.Series | None:
    if column_key in catalog.index:
        return catalog.loc[column_key]
    return None


def _extract_part_labels(
    metadata_before: pd.Series | None,
    metadata_after: pd.Series | None,
) -> tuple[str, str]:
    before = sanitize(metadata_before.part_label) if metadata_before is not None else ""
    after = sanitize(metadata_after.part_label) if metadata_after is not None else ""
    return before, after


def _is_numeric_label_variant(before: str, after: str) -> bool:
    if not before or not after:
        return False
    sanitized_before = sanitize(before)
    sanitized_after = sanitize(after)
    if not sanitized_before or not sanitized_after:
        return False
    if sanitized_before == sanitized_after:
        return False

    base_before = re.sub(r"\d+", "", sanitized_before)
    base_after = re.sub(r"\d+", "", sanitized_after)
    if base_before != base_after:
        return False

    digits_before = re.findall(r"\d+", sanitized_before)
    digits_after = re.findall(r"\d+", sanitized_after)
    return bool(digits_before and digits_after)


def _is_label_mismatch(
    old_value: str,
    new_value: str,
    label_before: str,
    label_after: str,
) -> bool:
    return bool(
        old_value
        and new_value
        and old_value == new_value
        and label_before
        and label_after
        and label_before != label_after
    )


def _resolve_block_and_station(
    metadata_before: pd.Series | None,
    metadata_after: pd.Series | None,
) -> tuple[str, str]:
    if metadata_before is None and metadata_after is None:
        return "", ""
    if metadata_before is None:
        assert metadata_after is not None
        return metadata_after.block, metadata_after.station
    if metadata_after is None:
        return metadata_before.block, metadata_before.station
    block = metadata_before.block or metadata_after.block
    station = metadata_before.station or metadata_after.station
    return block, station


def _determine_change_type(
    old_value: str,
    new_value: str,
    metadata_before: pd.Series | None,
    metadata_after: pd.Series | None,
    label_mismatch: bool,
    *,
    numeric_label_change: bool,
    same_part_label: bool,
    quantity_label: bool,
) -> str | None:
    if metadata_before is None:
        return "追加" if new_value else None
    if metadata_after is None:
        return "削除" if old_value else None
    if numeric_label_change:
        return "追加"
    if label_mismatch:
        return "名称不一致"
    if not old_value and new_value:
        return "追加"
    if old_value and not new_value:
        return "削除"
    if old_value == new_value:
        return None
    quantity_change = _classify_quantity_change(old_value, new_value)
    if quantity_change and (not same_part_label or quantity_label):
        return quantity_change
    if same_part_label and old_value and new_value:
        return "品番変更"
    return "変更"


def _collect_change_keywords(
    part_label_before: str,
    part_label_after: str,
    config: BopConfig,
) -> list[str]:
    keyword_set = set()
    if part_label_before:
        keyword_set.update(extract_keywords(part_label_before, config))
    if part_label_after:
        keyword_set.update(extract_keywords(part_label_after, config))
    return sorted(keyword_set)


def _is_quantity_label(label: str) -> bool:
    if not label:
        return False
    normalized = sanitize(label)
    if not normalized:
        return False
    quantity_keywords = ("数量", "個数", "台数", "本数", "pcs", "ＰＣＳ")
    return any(keyword in normalized for keyword in quantity_keywords)


def _parse_numeric(value: str) -> float | None:
    if not value:
        return None
    text = value.replace(",", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _classify_quantity_change(old_value: str, new_value: str) -> str | None:
    old_num = _parse_numeric(old_value)
    new_num = _parse_numeric(new_value)
    if old_num is None or new_num is None:
        return None
    if math.isclose(old_num, new_num, rel_tol=0.0, abs_tol=0.0):
        return None
    return "数量追加" if new_num > old_num else "数量減少"


def _realign_updated_columns(
    original_catalog: pd.DataFrame,
    updated_catalog: pd.DataFrame,
    updated_parts: pd.DataFrame,
    updated_annotations: dict[str, str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Rename updated columns so that existing BL/ST columns keep original keys."""
    rename_map = compute_column_alignment(original_catalog, updated_catalog)

    updated_annotations = updated_annotations or {}

    if not rename_map:
        return updated_catalog, updated_parts, updated_annotations

    target_keys = set(rename_map.values())
    collision_candidates = {
        key
        for key in updated_catalog.index
        if key not in rename_map and key in target_keys
    }
    collision_map: dict[str, str] = {}
    for key in collision_candidates:
        base = f"{key}__ins"
        suffix = 1
        candidate = base
        existing = (
            set(updated_catalog.index)
            .union(original_catalog.index)
            .union(collision_map.values())
        )
        while candidate in existing:
            suffix += 1
            candidate = f"{base}{suffix}"
        collision_map[key] = candidate
        existing.add(candidate)

    if collision_map:
        updated_parts = updated_parts.rename(columns=collision_map)
        updated_catalog = updated_catalog.rename(index=collision_map)
        updated_annotations = {
            collision_map.get(key, key): value
            for key, value in updated_annotations.items()
        }
        rename_map = {
            collision_map.get(src_key, src_key): dest_key
            for src_key, dest_key in rename_map.items()
        }

    aligned_parts = updated_parts.rename(columns=rename_map)
    aligned_catalog = updated_catalog.rename(index=rename_map)
    for orig_key in rename_map.values():
        if orig_key in original_catalog.index and orig_key in aligned_catalog.index:
            aligned_catalog.at[orig_key, "column_index"] = original_catalog.at[
                orig_key, "column_index"
            ]

    aligned_annotations: dict[str, str] = {}
    for key, value in updated_annotations.items():
        aligned_annotations[rename_map.get(key, key)] = value

    return aligned_catalog, aligned_parts, aligned_annotations


def detect_changes(
    variant_id: str,
    original_row: pd.Series,
    updated_row: pd.Series,
    column_catalog: pd.DataFrame,
    updated_catalog: pd.DataFrame,
    column_keys: Iterable[str],
    updated_annotations: dict[str, str] | None = None,
    config: BopConfig | None = None,
) -> list[ChangeRecord]:
    conf = config or get_bop_config()
    annotations = updated_annotations or {}
    changes: list[ChangeRecord] = []
    original_map = original_row.to_dict()
    updated_map = updated_row.to_dict()
    column_list = list(column_keys)
    key_index_map = {key: idx for idx, key in enumerate(column_list)}

    def _get_part_label_for_key(key: str | None) -> str:
        if key is None:
            return ""
        metadata = _lookup_metadata(key, column_catalog)
        if metadata is None:
            metadata = _lookup_metadata(key, updated_catalog)
        if metadata is None:
            return ""
        return sanitize(str(metadata.part_label))

    def _diff_single(column_key: str) -> list[ChangeRecord]:
        metadata_before = _lookup_metadata(column_key, column_catalog)
        metadata_after = _lookup_metadata(column_key, updated_catalog)
        if metadata_before is None and metadata_after is None:
            return []
        old_value = normalize_part_value(original_map.get(column_key, ""))
        new_value = normalize_part_value(updated_map.get(column_key, ""))
        part_label_before, part_label_after = _extract_part_labels(
            metadata_before, metadata_after
        )

        if (
            metadata_before is not None
            and metadata_after is not None
            and old_value == new_value
            and part_label_before == part_label_after
        ):
            return []

        label_mismatch = _is_label_mismatch(
            old_value, new_value, part_label_before, part_label_after
        )
        numeric_label_change = False
        same_part_label = bool(
            part_label_before
            and part_label_after
            and part_label_before == part_label_after
        )
        quantity_label = _is_quantity_label(part_label_before) or _is_quantity_label(
            part_label_after
        )
        if label_mismatch:
            numeric_label_change = _is_numeric_label_variant(
                part_label_before, part_label_after
            )
            if numeric_label_change:
                label_mismatch = False

        change_type = _determine_change_type(
            old_value,
            new_value,
            metadata_before,
            metadata_after,
            label_mismatch,
            numeric_label_change=numeric_label_change,
            same_part_label=same_part_label,
            quantity_label=quantity_label,
        )
        if change_type is None:
            return []

        block, station = _resolve_block_and_station(metadata_before, metadata_after)
        keywords = _collect_change_keywords(part_label_before, part_label_after, conf)

        index_pos = key_index_map.get(column_key)
        prev_key = (
            column_list[index_pos - 1]
            if index_pos is not None and index_pos > 0
            else None
        )
        next_key = (
            column_list[index_pos + 1]
            if index_pos is not None and index_pos < len(column_list) - 1
            else None
        )

        preceding_part_label = _get_part_label_for_key(prev_key) or None
        following_part_label = _get_part_label_for_key(next_key) or None

        preceding_original_value = (
            normalize_part_value(original_map.get(prev_key, ""))
            if prev_key is not None
            else ""
        )
        preceding_new_value = (
            normalize_part_value(updated_map.get(prev_key, ""))
            if prev_key is not None
            else ""
        )
        following_original_value = (
            normalize_part_value(original_map.get(next_key, ""))
            if next_key is not None
            else ""
        )
        following_new_value = (
            normalize_part_value(updated_map.get(next_key, ""))
            if next_key is not None
            else ""
        )

        record_old_value = (
            "" if (numeric_label_change and change_type == "追加") else old_value
        )

        return [
            ChangeRecord(
                variant_id=variant_id,
                block=block,
                station=station,
                part_label=part_label_after or part_label_before,
                column_key=column_key,
                original_value=record_old_value,
                new_value=new_value,
                change_type=change_type,
                keywords=keywords,
                change_id=generate_change_id(variant_id, block, station, column_key),
                original_part_label=part_label_before or None,
                updated_part_label=part_label_after or None,
                is_label_mismatch=label_mismatch,
                shape_feature=annotations.get(column_key),
                preceding_part_label=preceding_part_label,
                following_part_label=following_part_label,
                preceding_original_value=preceding_original_value or None,
                preceding_new_value=preceding_new_value or None,
                following_original_value=following_original_value or None,
                following_new_value=following_new_value or None,
            )
        ]

    change_batches = parallel_map(_diff_single, column_list) if column_list else []
    for batch in change_batches:
        if batch:
            changes.extend(batch)
    return changes


def compare_bop_tables(
    original_df: pd.DataFrame,
    updated_df: pd.DataFrame,
    original_catalog: pd.DataFrame,
    updated_catalog: pd.DataFrame,
    updated_annotations: dict[str, str] | None = None,
    config: BopConfig | None = None,
    *,
    max_workers: int | None = None,
) -> tuple[list[ChangeRecord], list[str], list[str]]:
    conf = config or get_bop_config()
    changes: list[ChangeRecord] = []
    removed_variants = [
        variant for variant in original_df.index if variant not in updated_df.index
    ]
    added_variants = [
        variant for variant in updated_df.index if variant not in original_df.index
    ]

    updated_catalog, updated_df, updated_annotations = _realign_updated_columns(
        original_catalog,
        updated_catalog,
        updated_df,
        updated_annotations,
    )

    column_keys = sorted(set(original_df.columns).union(updated_df.columns))

    jobs = [
        variant_id for variant_id in original_df.index if variant_id in updated_df.index
    ]

    def _diff_variant(variant_id: str) -> list[ChangeRecord]:
        original_row = original_df.loc[variant_id]
        updated_row = updated_df.loc[variant_id]
        return detect_changes(
            variant_id,
            original_row,
            updated_row,
            original_catalog,
            updated_catalog,
            column_keys,
            updated_annotations,
            conf,
        )

    change_batches = parallel_map(_diff_variant, jobs, max_workers=max_workers)
    for batch in change_batches:
        changes.extend(batch)

    return changes, added_variants, removed_variants


__all__ = [
    "compare_bop_tables",
    "detect_changes",
    "extract_keywords",
    "normalize_part_value",
]
