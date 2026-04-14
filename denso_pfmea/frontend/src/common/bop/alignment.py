from __future__ import annotations

import pandas as pd

from src.common.text_utils import sanitize


def compute_column_alignment(
    original_catalog: pd.DataFrame,
    updated_catalog: pd.DataFrame,
) -> dict[str, str]:
    """Return mapping of updated column keys to
    original column keys for stable alignment."""
    rename_map: dict[str, str] = {}
    if updated_catalog.empty or original_catalog.empty:
        return rename_map

    for block, new_group in updated_catalog.groupby("block"):
        if not block:
            continue
        orig_group = original_catalog[original_catalog["block"] == block]
        if orig_group.empty:
            continue

        orig_sorted = orig_group.sort_values("column_index")
        new_sorted = new_group.sort_values("column_index")
        orig_keys = list(orig_sorted.index)
        new_keys = list(new_sorted.index)

        def _index_value(frame: pd.DataFrame, key: str) -> int:
            value = frame.at[key, "column_index"] if key in frame.index else None
            if value is None:
                return 0
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        def _label(frame: pd.DataFrame, key: str) -> str:
            return sanitize(frame.at[key, "part_label"]) if key in frame.index else ""

        def _tokenize(frame: pd.DataFrame, key: str) -> str:
            label_text = _label(frame, key)
            if label_text:
                return label_text
            return f"__EMPTY__{_index_value(frame, key):04d}"

        orig_labels: list[str] = [_label(orig_sorted, key) for key in orig_keys]
        new_labels: list[str] = [_label(new_sorted, key) for key in new_keys]
        orig_tokens: list[str] = [_tokenize(orig_sorted, key) for key in orig_keys]
        new_tokens: list[str] = [_tokenize(new_sorted, key) for key in new_keys]

        m = len(orig_tokens)
        n = len(new_tokens)
        if m == 0 or n == 0:
            continue

        dp: list[list[int]] = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m):
            for j in range(n):
                if orig_tokens[i] == new_tokens[j]:
                    dp[i + 1][j + 1] = dp[i][j] + 1
                else:
                    dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])

        matched_pairs: list[tuple[int, int]] = []
        i, j = m, n
        while i > 0 and j > 0:
            if orig_tokens[i - 1] == new_tokens[j - 1]:
                matched_pairs.append((i - 1, j - 1))
                i -= 1
                j -= 1
            elif dp[i - 1][j] >= dp[i][j - 1]:
                i -= 1
            else:
                j -= 1

        matched_pairs.reverse()
        matched_orig = [False] * m
        matched_new = [False] * n
        for orig_idx, new_idx in matched_pairs:
            rename_map[new_keys[new_idx]] = orig_keys[orig_idx]
            matched_orig[orig_idx] = True
            matched_new[new_idx] = True

        # Fallback: attempt to align remaining elements
        # from the tail when labels are similar.
        from difflib import (
            SequenceMatcher,
        )  # local import to avoid global dependency when unused

        orig_unmatched = [idx for idx in range(m) if not matched_orig[idx]]
        new_unmatched = [idx for idx in range(n) if not matched_new[idx]]

        oi = len(orig_unmatched) - 1
        nj = len(new_unmatched) - 1
        while oi >= 0 and nj >= 0:
            orig_idx = orig_unmatched[oi]
            new_idx = new_unmatched[nj]
            similarity = SequenceMatcher(
                None, orig_labels[orig_idx], new_labels[new_idx]
            ).ratio()
            if similarity >= 0.6:
                rename_map[new_keys[new_idx]] = orig_keys[orig_idx]
                oi -= 1
                nj -= 1
            else:
                nj -= 1

    return rename_map


__all__ = ["compute_column_alignment"]
