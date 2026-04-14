from __future__ import annotations

from typing import Any, Mapping, Sequence

import streamlit as st

_STAGE_STATE_MAP = {
    "pending": "running",
    "running": "running",
    "complete": "complete",
    "error": "error",
}


def _format_stage_message(stage: Mapping[str, Any]) -> str:
    message = stage.get("message")
    if isinstance(message, str) and message.strip():
        return message
    state = stage.get("state", "pending")
    if state == "pending":
        return "待機中です…"
    if state == "running":
        return "処理中です…"
    if state == "complete":
        return "完了しました"
    if state == "error":
        return "エラーが発生しました"
    return ""


def render_dataset_load_progress(job_status: Mapping[str, Any]) -> None:
    """Render dataset load progress with per-stage status blocks.

    Note: This function was previously decorated with @st.fragment, but fragments
    that render UI elements cause warnings and this function needs to integrate
    with the main page flow for proper state updates.
    """

    details = job_status.get("details") if isinstance(job_status, Mapping) else None
    if not isinstance(details, Mapping):
        details = {}

    progress = details.get("progress", job_status.get("progress", 0))
    try:
        progress_value = int(progress)
    except (ValueError, TypeError):
        progress_value = 0
    progress_value = max(0, min(100, progress_value))

    active_label = details.get("active_stage_label") or "データセットを読み込んでいます"

    st.subheader("ファイル解析の進行状況")
    st.progress(progress_value, text=f"{active_label} ({progress_value}%)")

    stage_entries = details.get("stages")
    if not isinstance(stage_entries, Sequence):
        stage_entries = []

    for raw_stage in stage_entries:
        if not isinstance(raw_stage, Mapping):  # pragma: no cover - defensive guard
            continue
        stage_id = str(raw_stage.get("id", "stage"))
        stage_label = raw_stage.get("label") or stage_id
        stage_state = str(raw_stage.get("state", "pending"))
        status_state = _STAGE_STATE_MAP.get(stage_state, "running")
        status = st.status(
            stage_label,
            state=status_state,  # type: ignore[arg-type]
            expanded=True,
        )
        with status:
            message = _format_stage_message(raw_stage)
            if message:
                st.write(message)


__all__ = ["render_dataset_load_progress"]
