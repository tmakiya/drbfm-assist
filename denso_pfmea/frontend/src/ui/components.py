"""Reusable UI components for PFMEA application.

This module provides common UI building blocks used across the application,
including progress indicators, validation displays, and data tables.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import streamlit as st

from src.common.validation import ValidationIssue
from src.services.change_pipeline.models import ComparisonMode
from src.ui.view_models import ChangeImpactTableViewModel, VariantOverviewViewModel

# Component keys
VARIANT_SOURCE_SELECT_KEY = "variant_source_select"

# Layout constants (derived from design system spacing)
_TABLE_ROW_HEIGHT_PX = 35
_TABLE_MAX_VISIBLE_ROWS = 10
_TABLE_DEFAULT_HEIGHT = 350
_CHANGE_TABLE_HEIGHT = 420


class ProgressPanel:
    """Streamlit上の進捗バー／ステータス表示をまとめた軽量ヘルパ。

    プログレスバーのtext要素を使ってステータスを表示する。
    """

    def __init__(self) -> None:
        self._progress_placeholder = st.empty()
        self._value: int = 0
        self._label: str = ""

    @property
    def value(self) -> int:
        return self._value

    def clear(self) -> None:
        self._progress_placeholder.empty()
        self._value = 0
        self._label = ""

    def restore(self, status: Mapping[str, Any]) -> None:
        label = str(status.get("label", ""))
        kind = str(status.get("kind", "info"))
        value = status.get("value", 0)
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            numeric_value = 0
        details = status.get("details")
        self.update(value=numeric_value, label=label, kind=kind, details=details)

    def update(
        self,
        *,
        value: int,
        label: str,
        kind: str = "info",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        safe_value = max(0, min(100, int(value)))
        self._value = safe_value
        self._label = label

        self._progress_placeholder.progress(safe_value, text=label)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def render_validation_issues(label: str, issues: Iterable[ValidationIssue]) -> bool:
    has_error = False
    for issue in issues:
        message = f"{label}: {issue.message}"
        if issue.severity == "error":
            st.error(message)
            has_error = True
        else:
            st.warning(message)
    return has_error


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    match_length = 0
    for idx in range(limit):
        if left[idx] != right[idx]:
            break
        match_length += 1
    return match_length


def _select_source_variant_index(
    source_variants: Sequence[str], target_variant: str
) -> int:
    if not source_variants:
        return 0

    target = target_variant or ""
    best_index = 0
    best_score = -1
    best_is_full_match = False

    for idx, variant in enumerate(source_variants):
        score = _common_prefix_length(variant, target)
        is_full_match = score == len(variant)
        if score > best_score or (
            score == best_score and is_full_match and not best_is_full_match
        ):
            best_index = idx
            best_score = score
            best_is_full_match = is_full_match

    return best_index


def render_variant_overview(view_model: VariantOverviewViewModel) -> None:
    st.subheader("編成表サマリー")

    source_header_cols = st.columns([6, 1])
    source_header_cols[0].markdown("**流用元編成表**")
    source_header_cols[1].markdown(f"バリエーション数 {view_model.source_count}件")

    source_row_count = len(view_model.source_metadata)
    source_height = (
        min(source_row_count, _TABLE_MAX_VISIBLE_ROWS) * _TABLE_ROW_HEIGHT_PX
        or _TABLE_DEFAULT_HEIGHT
    )
    st.dataframe(
        view_model.source_metadata,
        width="stretch",
        hide_index=True,
        height=source_height or _TABLE_DEFAULT_HEIGHT,
    )

    st.markdown("**変更後の編成表**")
    st.dataframe(
        view_model.target_metadata,
        width="stretch",
        hide_index=True,
    )

    if view_model.multiple_target_rows:
        st.warning(
            "変更後編成表に複数行が含まれています。解析では先頭の1行のみを使用します。"
        )


def render_variant_selector(
    view_model: VariantOverviewViewModel,
    *,
    disabled: bool = False,
) -> tuple[str, str, ComparisonMode] | None:
    st.subheader("比較バリエーション選択")
    if not view_model.source_variants:
        st.error("流用元編成表に有効なバリエーションが見つかりません。")
        return None
    if not view_model.target_variants:
        st.error(
            "比較対象のバリエーションが取得できませんでした。編成表の行構成を確認してください。"
        )
        return None

    selector_cols = st.columns([2, 1])
    selected_target = view_model.primary_target_variant
    if not selected_target:
        st.error(
            "変更後編成表の比較対象行を取得できませんでした。ファイル内容を確認してください。"
        )
        return None

    # プルダウンの先頭に「全バリエーション比較」オプションを追加
    # 全バリエーション比較: 流用元の全行をベースラインとして、
    # 既に他バリエーションに存在する部品変更を除外するフィルタを適用
    all_variants_label = "全バリエーション比較（既存部品を除外）"
    source_options = [all_variants_label] + list(view_model.source_variants)
    default_index = _select_source_variant_index(
        list(view_model.source_variants), selected_target
    )
    # 「全バリエーション」が追加されているので、インデックスを+1する
    default_index = default_index + 1

    selected_source = selector_cols[0].selectbox(
        "流用元バリエーション",
        source_options,
        index=default_index,
        disabled=disabled,
        key=VARIANT_SOURCE_SELECT_KEY,
    )

    # 選択に基づいてComparisonModeを判定
    if selected_source == all_variants_label:
        comparison_mode = ComparisonMode.ALL_VARIANTS
        # ALL_VARIANTSの場合、実際のバリエーション名として最初のものを使用
        actual_source = list(view_model.source_variants)[0]
    else:
        comparison_mode = ComparisonMode.SINGLE_VARIANT
        actual_source = selected_source

    target_col = selector_cols[1]
    target_col.markdown("**変更後バリエーション**")
    target_col.markdown(selected_target)
    if view_model.multiple_target_rows:
        target_col.warning(
            "変更後編成表に複数行が含まれています。先頭の1行のみを比較対象とします。"
        )

    return actual_source, selected_target, comparison_mode


def render_change_impact_table(view_model: ChangeImpactTableViewModel) -> None:
    """Render the change impact table.

    Note: This function was previously decorated with @st.fragment, but fragments
    can cause display inconsistencies during state transitions (e.g., analysis
    results appearing faintly during LLM processing). Removed to ensure clean
    rendering: either fully visible or not rendered at all.
    """
    if not view_model.rows:
        st.info("変化点が見つかりましたが、表示可能なPFMEA情報がありません。")
        return

    column_config = {
        "ブロック": st.column_config.TextColumn("ブロック", width="small"),
        "ステーション": st.column_config.TextColumn("ステーション", width="small"),
        "対象部品": st.column_config.TextColumn("対象部品", width="medium"),
        "形状の特長": st.column_config.TextColumn("形状の特長", width="large"),
        "変更種別": st.column_config.TextColumn("変更種別", width="small"),
        "品番": st.column_config.TextColumn("品番", width="medium"),
        "差異理由": st.column_config.TextColumn("差異理由", width="large"),
    }

    df = view_model.display_df
    if "形状の特長" not in df.columns:
        column_config.pop("形状の特長", None)

    st.dataframe(
        df,
        width="stretch",
        height=_CHANGE_TABLE_HEIGHT,
        column_config=column_config,
        hide_index=True,
    )


__all__ = [
    "ProgressPanel",
    "render_change_impact_table",
    "render_validation_issues",
    "render_variant_overview",
    "render_variant_selector",
]
