"""LLM metrics display components.

This module provides UI components for displaying AI inference metrics,
including total requests, latency statistics, and operation-level details.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from src.ui.shared_constants import ICON_WARNING

_FRAGMENTS_ENABLED = os.getenv("SOL_PFMEA_ENABLE_FRAGMENTS", "").lower() in {
    "1",
    "true",
    "yes",
}


def _fragment(func: Callable[..., Any]) -> Callable[..., Any]:
    if _FRAGMENTS_ENABLED and hasattr(st, "fragment"):
        return st.fragment(func)
    return func


# Threshold for warning display
_MALFORMED_WARNING_THRESHOLD = 0
_RATE_LIMIT_WARNING_THRESHOLD = 3


@_fragment
def render_metrics_summary(metrics: Mapping[str, Any]) -> None:
    """Display comprehensive AI inference metrics.

    Shows overall totals and per-operation statistics in an expandable format.
    Uses Streamlit metrics widgets for key performance indicators.
    Displays warnings when malformed responses or rate limit hits exceed thresholds.

    Args:
        metrics: Dictionary containing 'totals' and 'operations' data.
            Expected structure:
            {
                "totals": {
                    "total_calls": int,
                    "avg_latency_ms": float,
                    "p95_latency_ms": float,
                    "rate_limit_hits": int,
                    "malformed_responses": int
                },
                "operations": {
                    "operation_name": {
                        "total_calls": int,
                        "success_calls": int,
                        "avg_latency_ms": float,
                        "p95_latency_ms": float,
                        "malformed_responses": int
                    }
                }
            }
    """
    if not metrics:
        return

    totals = metrics.get("totals") or {}
    operations = metrics.get("operations") or {}

    st.caption("AI推定メトリクス")

    # Display summary metrics in a single row
    summary_cols = st.columns(5)
    summary_cols[0].metric("総リクエスト", totals.get("total_calls", 0))
    summary_cols[1].metric("平均応答(ms)", totals.get("avg_latency_ms", 0.0))
    summary_cols[2].metric("P95応答(ms)", totals.get("p95_latency_ms", 0.0))
    summary_cols[3].metric("レート制限", totals.get("rate_limit_hits", 0))
    summary_cols[4].metric("不正応答", totals.get("malformed_responses", 0))

    # Display warnings for malformed responses
    malformed_count = totals.get("malformed_responses", 0)
    if malformed_count > _MALFORMED_WARNING_THRESHOLD:
        st.warning(
            f"{ICON_WARNING} JSON解析に問題のある応答が {malformed_count} 件検出されました。"
            "Structured Output スキーマ検証に失敗したレスポンスです。"
        )

    # Display warnings for rate limit hits
    rate_limit_count = totals.get("rate_limit_hits", 0)
    if rate_limit_count > _RATE_LIMIT_WARNING_THRESHOLD:
        st.warning(
            f"{ICON_WARNING} レート制限により {rate_limit_count} 回のリトライが発生しました。"
            "API呼び出しの頻度を調整することを検討してください。"
        )

    if not operations:
        return

    # Display per-operation details in expandable section
    with st.expander("操作別詳細", expanded=False):
        for operation, snapshot in operations.items():
            st.write(f"**{operation}**")
            op_cols = st.columns(5)
            op_cols[0].metric("呼び出し", snapshot.get("total_calls", 0))
            op_cols[1].metric("成功", snapshot.get("success_calls", 0))
            op_cols[2].metric("平均(ms)", snapshot.get("avg_latency_ms", 0.0))
            op_cols[3].metric("P95(ms)", snapshot.get("p95_latency_ms", 0.0))
            op_cols[4].metric("不正応答", snapshot.get("malformed_responses", 0))


__all__ = ["render_metrics_summary"]
