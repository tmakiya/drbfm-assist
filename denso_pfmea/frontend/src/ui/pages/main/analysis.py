from __future__ import annotations

from typing import Any

import streamlit as st

from src.services.change_pipeline.models import ComparisonMode
from src.ui import components as ui_components
from src.ui.state import SessionManager
from src.ui.view_models import ChangeImpactTableViewModel

from .llm_section import render_llm_results


def get_change_report_excel(session_manager: SessionManager) -> bytes | None:
    """変化点レポートのExcelデータを取得する。"""
    analysis_result = session_manager.get_analysis_result()
    if analysis_result is None or not analysis_result.has_changes:
        return None
    table_view_model = ChangeImpactTableViewModel.from_sources(
        analysis_result.change_report
    )
    if not table_view_model.rows:
        return None
    return table_view_model.xlsx_bytes()


def render_change_analysis(
    session_manager: SessionManager,
    analysis_result: Any,
) -> None:
    if not analysis_result.has_changes:
        st.info("流用元と変更後で変化点が見つかりませんでした。")
        return

    if analysis_result.has_label_mismatch:
        st.error(
            "品番が同一のまま部品名称が変更されています。入力データを確認してください。"
        )

    table_view_model = ChangeImpactTableViewModel.from_sources(
        analysis_result.change_report
    )

    mode_labels = {
        ComparisonMode.SINGLE_VARIANT: "特定バリエーション比較",
        ComparisonMode.ALL_VARIANTS: "全バリエーション比較",
    }
    stats = analysis_result.comparison_stats
    stats_text = (
        f"比較モード: {mode_labels.get(analysis_result.comparison_mode, analysis_result.comparison_mode.value)} "
        f"/ 変化点: {stats.actionable}件"
    )

    st.subheader("流用元との変化点")
    st.caption(stats_text)
    ui_components.render_change_impact_table(table_view_model)

    st.markdown("---")
    st.subheader("AI推定")


def render_llm_section(
    session_manager: SessionManager,
    analysis_result: Any,
) -> None:
    """AI推定結果を表示する（ProgressPanelの後に呼び出す）"""
    render_llm_results(
        session_manager,
        analysis_result.actionable_changes,
        analysis_result.pfmea_context,
    )


__all__ = ["get_change_report_excel", "render_change_analysis", "render_llm_section"]
