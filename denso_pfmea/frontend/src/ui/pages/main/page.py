from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from src.common.perf import record_event, time_block
from src.services.change_pipeline import (
    ComparisonMode,
    build_change_analysis,
    build_variant_overview,
)
from src.ui import components as ui_components
from src.ui.state import SessionManager, get_session_manager
from src.ui.theme import ensure_auto_theme

from .analysis import render_change_analysis, render_llm_section
from .constants import (
    DEFAULT_VERTEX_MODEL,
    DEFAULT_VERTEX_REGION,
    LLM_MODE_INFO,
    LLM_MODE_ORDER,
    PRO_VERTEX_MODEL,
)
from .data_loaders import (
    build_dataset_signature,
    collect_missing_inputs,
    get_uploaded_files_from_sidebar,
    load_datasets_with_spinner,
)
from .environment import ensure_env_loaded
from .llm_coordinator import (
    MAX_POLL_TIMEOUT_SECONDS,
    _calculate_progress,
    _process_workflow_result,
    start_llm_workflow,
)
from .module_loader import get_bop_module
from .validators import validate_uploaded_datasets

logger = logging.getLogger(__name__)

ANALYSIS_PROGRESS_MAX = 20
LLM_MODE_SELECTOR_KEY = "llm_mode_selector"
LLM_TRIGGER_BUTTON_KEY = "llm_trigger_button"
ANALYSIS_TRIGGER_BUTTON_KEY = "analysis_trigger_button"
LLM_POLLING_KEY = "llm_job_polling"
LLM_POLL_INTERVAL_SECONDS = 3.0

# Fragment 有効化フラグ（デフォルト: 有効、SOL_PFMEA_ENABLE_FRAGMENTS=false で無効化可能）
_FRAGMENTS_ENABLED = os.getenv("SOL_PFMEA_ENABLE_FRAGMENTS", "true").lower() in {
    "1",
    "true",
    "yes",
}


def _fragment(func: Callable[..., Any]) -> Callable[..., Any]:
    if _FRAGMENTS_ENABLED and hasattr(st, "fragment"):
        return st.fragment(func)
    return func


def _rerun_app(*, reason: str, job_id: str | None = None) -> None:
    """アプリ全体をリランする。"""
    st.rerun()


def format_comparison_label(
    source_variant: str,
    target_variant: str,
    *,
    comparison_mode: ComparisonMode = ComparisonMode.SINGLE_VARIANT,
    source_variant_count: int | None = None,
) -> str:
    if comparison_mode == ComparisonMode.ALL_VARIANTS:
        if source_variant_count and source_variant_count > 0:
            base_label = f"全{source_variant_count}バリエーション"
        else:
            base_label = "全バリエーション"
        return f"{base_label} → {target_variant}" if target_variant else base_label

    if source_variant == target_variant:
        return source_variant
    return f"{source_variant} → {target_variant}"


def setup_page() -> None:
    with time_block("setup_page.ensure_env_loaded", metadata={"phase": "ui"}):
        ensure_env_loaded()

    with time_block("setup_page.ensure_auto_theme", metadata={"phase": "ui"}):
        ensure_auto_theme(page_title="CADDi AI-PFMEA", layout="wide")

    with time_block("setup_page.render_header", metadata={"phase": "ui"}):
        st.title("CADDi AI-PFMEA")


def _handle_dataset_uploads(
    manager: SessionManager,
) -> tuple[tuple[Any, Any, Any], str] | None:
    """Handle dataset uploads with synchronous loading."""
    source_file, target_file, pfmea_file = get_uploaded_files_from_sidebar(manager)

    missing_inputs = collect_missing_inputs(source_file, target_file, pfmea_file)
    if missing_inputs:
        record_event(
            "await_required_inputs",
            metadata={"phase": "ui", "missing": tuple(missing_inputs)},
        )
        st.info("ファイルをアップロードしてください: " + ", ".join(missing_inputs))
        return None

    if source_file is None or target_file is None or pfmea_file is None:
        return None

    source_bytes = source_file.getvalue()
    target_bytes = target_file.getvalue()
    pfmea_bytes = pfmea_file.getvalue()

    dataset_signature = build_dataset_signature(source_bytes, target_bytes, pfmea_bytes)

    # 同期的にデータセットを読み込み（spinner表示）
    datasets = load_datasets_with_spinner(source_bytes, target_bytes, pfmea_bytes)
    if datasets is None or not validate_uploaded_datasets(*datasets):
        return None

    source_dataset, target_dataset, pfmea_dataset = datasets
    manager.dataset_changed(dataset_signature)

    return (source_dataset, target_dataset, pfmea_dataset), dataset_signature


def _update_status(
    manager: SessionManager,
    panel: ui_components.ProgressPanel,
    *,
    kind: str,
    label: str,
    value: int,
    details: Mapping[str, Any] | None = None,
) -> None:
    manager.set_analysis_status(label=label, value=value, kind=kind, details=details)
    panel.update(value=value, label=label, kind=kind, details=details)


def _start_llm_job(
    manager: SessionManager,
    analysis_result: Any,
) -> bool:
    """Start LLM workflow synchronously (no background thread).

    Returns True if workflow started successfully.
    """
    thread_id = start_llm_workflow(
        manager,
        analysis_result.actionable_changes,
        analysis_result.pfmea_context,
        env=os.environ,
    )

    if thread_id:
        st.session_state[LLM_POLLING_KEY] = True
        return True
    return False


def _create_llm_polling_fragment(
    manager: SessionManager,
    panel: ui_components.ProgressPanel,
) -> Callable[[], None]:
    """Create a polling fragment that directly polls the backend API.

    IMPORTANT: run_every is evaluated when @st.fragment is applied, so we must
    create the fragment with the correct run_every value BEFORE calling it.
    When job completes, we use st.rerun() to re-create with run_every=None.
    """
    is_polling = st.session_state.get(LLM_POLLING_KEY, False)
    run_every = LLM_POLL_INTERVAL_SECONDS if is_polling else None

    if _FRAGMENTS_ENABLED and hasattr(st, "fragment"):
        decorator = st.fragment(run_every=run_every)
    else:
        decorator = lambda f: f  # noqa: E731

    @decorator
    def _poll_backend_directly() -> None:
        """Poll backend API directly for workflow status.

        This fragment auto-refreshes every LLM_POLL_INTERVAL_SECONDS when polling.
        On job completion, sets LLM_POLLING_KEY=False and calls st.rerun()
        to re-create the fragment with run_every=None (stops auto-refresh).
        """
        from src.client import (
            get_auth_headers,
            get_langgraph_client,
            get_workflow_result,
            get_workflow_state,
        )

        workflow_info = manager.get_llm_workflow_info()
        if not workflow_info:
            st.session_state[LLM_POLLING_KEY] = False
            return

        thread_id = workflow_info["thread_id"]
        total_requests = workflow_info["total_requests"]
        started_at = workflow_info["started_at"]

        # Timeout check
        elapsed = time.time() - started_at
        if elapsed > MAX_POLL_TIMEOUT_SECONDS:
            _update_status(
                manager,
                panel,
                kind="error",
                label=f"タイムアウトしました（{int(elapsed)}秒）",
                value=ANALYSIS_PROGRESS_MAX,
            )
            manager.cleanup_after_workflow()
            manager.set_analysis_running(False)
            st.session_state[LLM_POLLING_KEY] = False
            st.rerun()
            return

        # Poll backend for status
        try:
            client = get_langgraph_client(headers=get_auth_headers())
            state = get_workflow_state(client, thread_id)
        except Exception as e:
            logger.error("Poll error: %s", e)
            # Continue polling on next interval
            return

        status = state.get("status", "unknown")
        values = state.get("values", {})

        if status == "completed":
            # Fetch final result
            try:
                result = get_workflow_result(client, thread_id)
            except Exception as e:
                logger.error("Failed to get workflow result: %s", e)
                _update_status(
                    manager,
                    panel,
                    kind="error",
                    label=f"結果取得に失敗しました: {e}",
                    value=ANALYSIS_PROGRESS_MAX,
                )
                manager.cleanup_after_workflow()
                manager.set_analysis_running(False)
                st.session_state[LLM_POLLING_KEY] = False
                st.rerun()
                return

            success, error = _process_workflow_result(manager, result)

            if success:
                _update_status(
                    manager,
                    panel,
                    kind="success",
                    label="AI推定が完了しました",
                    value=100,
                )
            else:
                _update_status(
                    manager,
                    panel,
                    kind="error",
                    label=error or "エラーが発生しました",
                    value=ANALYSIS_PROGRESS_MAX,
                )

            # ワークフロー完了後のクリーンアップ
            manager.cleanup_after_workflow()
            manager.set_analysis_running(False)
            st.session_state[LLM_POLLING_KEY] = False
            st.rerun()
        else:
            # Update progress based on current phase
            current_phase = values.get("current_phase", "")
            completed_count = values.get("completed_count", 0)
            phase_message = values.get("phase_message", "処理中...")

            progress = _calculate_progress(current_phase)

            kind = "error" if current_phase == "error" else "info"
            _update_status(
                manager,
                panel,
                kind=kind,
                label=phase_message or f"処理中: {current_phase}",
                value=progress,
                details={
                    "phase": f"executing_{current_phase}",
                    "completed_count": completed_count,
                    "total_requests": total_requests,
                },
            )

    return _poll_backend_directly


@_fragment
def _render_llm_mode_selector(manager: SessionManager, *, disabled: bool) -> None:
    """LLMモード選択をフラグメント化して全体リランを防止"""
    mode_order = list(LLM_MODE_ORDER)
    preferred_model = manager.get_preferred_vertex_model() or DEFAULT_VERTEX_MODEL
    if preferred_model not in mode_order:
        preferred_model = DEFAULT_VERTEX_MODEL

    def _format_mode_option(model_name: str) -> str:
        info = LLM_MODE_INFO.get(model_name, {"label": model_name})
        return info.get("label", model_name)

    selected_model = st.pills(
        "LLM推定モード",
        options=mode_order,
        default=preferred_model,
        format_func=_format_mode_option,
        selection_mode="single",
        disabled=disabled,
        label_visibility="collapsed",
        key=LLM_MODE_SELECTOR_KEY,
    )
    if selected_model:
        manager.set_preferred_vertex_model(selected_model)


def _render_llm_trigger(manager: SessionManager, *, disabled: bool) -> None:
    """LLMトリガーボタンとダウンロードボタンを横に並べて表示"""
    from .llm_results_renderer import render_llm_download_button

    def _trigger_llm() -> None:
        manager.clear_llm_results()
        manager.request_llm_run()
        # ボタンクリック時にポーリングフラグをセットして、リロード後すぐにUIをdisabledにする
        st.session_state[LLM_POLLING_KEY] = True

    # LLM結果があるかどうかでボタンのスタイルを変更
    llm_data = manager.get_llm_structured_rows()
    has_llm_results = bool(llm_data.get("by_change"))
    button_label = "AI推定を再実行" if has_llm_results else "AI推定を実行"
    button_type = "secondary" if has_llm_results else "primary"

    with st.container(horizontal=True):
        st.button(
            button_label,
            type=button_type,
            disabled=disabled,
            on_click=_trigger_llm,
            key=LLM_TRIGGER_BUTTON_KEY,
        )
        render_llm_download_button(manager, key="llm_download_header")


def render_main_page(session_manager: SessionManager | None = None) -> None:
    setup_page()
    manager = session_manager or get_session_manager()

    try:
        dataset_payload = _handle_dataset_uploads(manager)
        if dataset_payload is None:
            return

        (source_dataset, target_dataset, pfmea_dataset), dataset_signature = (
            dataset_payload
        )

        overview_vm = build_variant_overview(source_dataset, target_dataset)
        ui_components.render_variant_overview(overview_vm)

        # AI推定ポーリング中のみUIをdisabledにする
        is_llm_running = st.session_state.get(LLM_POLLING_KEY, False)
        selection = ui_components.render_variant_selector(
            overview_vm,
            disabled=is_llm_running,
        )
        if selection is None:
            return

        selected_source_variant, selected_target_variant, comparison_mode = (
            selection
        )

        # 前回のComparisionModeと比較してmode_changedを判定
        previous_mode = manager.get_comparison_mode()
        mode_changed = previous_mode != comparison_mode
        if mode_changed:
            manager.set_comparison_mode(comparison_mode)
        comparison_label = format_comparison_label(
            selected_source_variant,
            selected_target_variant,
            comparison_mode=comparison_mode,
            source_variant_count=overview_vm.source_count,
        )

        previous_selection = manager.get_analysis_selection()
        current_selection = (selected_source_variant, selected_target_variant)
        selection_changed = previous_selection != current_selection
        context_changed = selection_changed or mode_changed
        if context_changed:
            manager.clear_analysis_result()
            manager.update_analysis_selection(current_selection)

        # 解析処理（ボタン表示前に実行して最新の状態を反映）
        analysis_requested = manager.consume_analysis_request()
        if analysis_requested:
            manager.clear_llm_results()
            manager.clear_analysis_status()
            with st.spinner("変化点解析を実行中..."):
                analysis_result = build_change_analysis(
                    variant_label=comparison_label,
                    source_dataset=source_dataset,
                    target_dataset=target_dataset,
                    selected_source_variant=selected_source_variant,
                    selected_target_variant=selected_target_variant,
                    pfmea_dataset=pfmea_dataset,
                    bop_config=get_bop_module().get_bop_config(),
                    comparison_mode=comparison_mode,
                )
            manager.set_analysis_result(analysis_result)
            manager.update_analysis_selection(
                (selected_source_variant, selected_target_variant)
            )
            manager.set_analysis_running(False)

        analysis_result = manager.get_analysis_result()

        # 解析ボタン
        def _trigger_analysis() -> None:
            manager.request_analysis_run()

        is_first_analysis = analysis_result is None
        button_label = "変化点解析" if is_first_analysis else "変化点解析を再実行"
        button_type = "primary" if is_first_analysis else "secondary"
        with st.container(horizontal=True):
            st.button(
                button_label,
                type=button_type,
                disabled=is_llm_running,
                on_click=_trigger_analysis,
                key=ANALYSIS_TRIGGER_BUTTON_KEY,
            )
            # 変化点結果がある場合はダウンロードボタンを表示
            if not is_first_analysis:
                from .analysis import get_change_report_excel
                excel_data = get_change_report_excel(manager)
                if excel_data:
                    st.download_button(
                        label="変化点をExcelとしてダウンロード",
                        data=excel_data,
                        file_name="pfmea_change_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="change_report_download_header",
                    )

        if analysis_result is None:
            return

        # 解析結果表示（変化点テーブル + AI推定ヘッダー）
        render_change_analysis(manager, analysis_result)

        # AI推定ボタン
        _render_llm_trigger(manager, disabled=is_llm_running)

        # ProgressPanel（AI推定進捗専用、結果の上に表示）
        progress_panel = ui_components.ProgressPanel()
        stored_status = manager.get_analysis_status()

        # AI推定中またはステータスがある場合のみ進捗表示を復元
        if stored_status and not context_changed:
            progress_panel.restore(stored_status)
        elif not is_llm_running:
            # AI推定開始前は進捗バーを非表示
            progress_panel.clear()

        # AI推定結果表示（ProgressPanelの下）
        render_llm_section(manager, analysis_result)

        llm_requested = manager.consume_llm_request()
        if llm_requested:
            analysis_result = manager.get_analysis_result()
            if analysis_result is not None:
                with st.spinner("ワークフローを開始中..."):
                    success = _start_llm_job(manager, analysis_result)
                if success:
                    _update_status(
                        manager,
                        progress_panel,
                        kind="info",
                        label="AI推定を開始しています...",
                        value=ANALYSIS_PROGRESS_MAX,
                    )
                else:
                    _update_status(
                        manager,
                        progress_panel,
                        kind="error",
                        label="ワークフロー開始に失敗しました",
                        value=ANALYSIS_PROGRESS_MAX,
                    )
                    manager.set_analysis_running(False)
            else:
                manager.set_analysis_running(False)

        # LLMポーリング（session_stateを直接参照して最新の状態を取得）
        if st.session_state.get(LLM_POLLING_KEY, False):
            poll_fragment = _create_llm_polling_fragment(manager, progress_panel)
            poll_fragment()
    except Exception:
        error_id = f"ui-{int(time.time() * 1000)}"
        logger.exception(
            "UI render failed",
            extra={"error_id": error_id, "stage": "render_main_page"},
        )
        st.error(
            "画面描画中にエラーが発生しました。再読み込みしてください。"
            f"(error_id={error_id})"
        )


__all__ = [
    "DEFAULT_VERTEX_MODEL",
    "DEFAULT_VERTEX_REGION",
    "PRO_VERTEX_MODEL",
    "format_comparison_label",
    "render_main_page",
    "setup_page",
]
