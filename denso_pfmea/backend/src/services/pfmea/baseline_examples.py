from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

from src.services.pfmea_context import PfmeaContext


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_normalize_value(item) for item in value if item is not None)
    return str(value)


def collect_baseline_examples(
    contexts: Iterable[PfmeaContext | None],
    *,
    process_name: str | None = None,
    limit: int = 5,
) -> tuple[dict[str, str], ...]:
    """Collect representative PFMEA rows to use as reference examples.

    Args:
        contexts: Iterable of PFMEA context bundles.
        process_name: Optional process name filter. When provided, only rows whose
            process_name matches (case-insensitive) are used when available.
        limit: Maximum number of examples to return.

    Returns:
        Tuple of dictionaries representing PFMEA rows.
    """
    examples: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    target_name = process_name.strip() if process_name else None

    for context in contexts:
        if context is None or context.data is None or context.data.empty:
            continue

        working = context.data
        filtered = working
        if target_name and "process_name" in working.columns:
            mask = (
                working["process_name"].astype(str).str.strip().str.casefold()
                == target_name.casefold()
            )
            if mask.any():
                filtered = working.loc[mask]

        if filtered.empty:
            filtered = working

        for _, row in filtered.iterrows():
            requirement = _normalize_value(row.get("requirement", "")).strip()
            failure_mode = _normalize_value(row.get("failure_mode", "")).strip()
            cause = _normalize_value(row.get("cause", "")).strip()
            dedup_key = (requirement, failure_mode, cause)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            record = {
                str(column): _normalize_value(value) for column, value in row.items()
            }
            examples.append(record)
            if len(examples) >= limit:
                return tuple(examples)

    return tuple(examples)


def format_baseline_examples_json(
    examples: Sequence[Mapping[str, str]],
    *,
    empty_message: str = "該当工程の既存PFMEAエントリは確認できませんでした。",
) -> str:
    """Serialize baseline examples as JSON code block for prompts."""
    if not examples:
        return empty_message

    payload = [
        {str(key): str(value) for key, value in example.items()} for example in examples
    ]
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


__all__ = [
    "collect_baseline_examples",
    "format_baseline_examples_json",
]
