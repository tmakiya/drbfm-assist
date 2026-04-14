from __future__ import annotations

import hashlib
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import streamlit as st

from src.common.concurrency import ParallelExecutionError, parallel_map

from .constants import PFMEA_BLOCKS
from .module_loader import get_bop_module, get_pfmea_module, get_streamlit_task_wrapper

if TYPE_CHECKING:
    from src.ui.state import SessionManager

SOURCE_FILE_UPLOADER_KEY = "sidebar_source_bop_uploader"
TARGET_FILE_UPLOADER_KEY = "sidebar_target_bop_uploader"
PFMEA_FILE_UPLOADER_KEY = "sidebar_pfmea_uploader"


def _run_parallel_dataset_tasks(
    tasks: Sequence[tuple[str, Callable[[], Any]]],
    *,
    wrapper: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute dataset loading tasks in parallel."""

    def _execute_task(task: tuple[str, Callable[[], Any]]) -> tuple[str, Any]:
        stage_id, func = task
        result = func()
        return stage_id, result

    executor = _execute_task
    if wrapper is not None:
        executor = wrapper(_execute_task)

    results = parallel_map(
        executor,
        tasks,
        max_workers=len(tasks),
    )
    return dict(results)


def _has_streamlit_context() -> bool:
    try:
        from streamlit.runtime.scriptrunner import (
            get_script_run_ctx,
        )
    except (ImportError, RuntimeError):
        return False
    try:
        ctx = get_script_run_ctx(suppress_warning=True)
    except TypeError:
        ctx = get_script_run_ctx()
    return ctx is not None


def _load_bop_master_uncached(data: bytes) -> Any:
    bop_module = get_bop_module()
    return bop_module.load_bop_master(data)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=10)
def load_bop_master(data: bytes) -> Any:
    """Load BOP master data with caching.

    Cached by file content hash to avoid re-parsing on reruns.
    TTL: 1 hour, max 10 entries to prevent unbounded cache growth.
    """
    return _load_bop_master_uncached(data)


def _load_pfmea_uncached(data: bytes) -> Any:
    pfmea_module = get_pfmea_module()
    return pfmea_module.load_pfmea_bundle(data, PFMEA_BLOCKS)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=10)
def load_pfmea(data: bytes) -> Any:
    """Load PFMEA bundle data with caching.

    Cached by file content hash to avoid re-parsing on reruns.
    TTL: 1 hour, max 10 entries to prevent unbounded cache growth.
    """
    return _load_pfmea_uncached(data)


def collect_missing_inputs(
    source_file: Any, target_file: Any, pfmea_file: Any
) -> list[str]:
    missing = []
    if source_file is None:
        missing.append("流用元編成表 (Excel)")
    if target_file is None:
        missing.append("変更後の編成表 (Excel)")
    if pfmea_file is None:
        missing.append("PFMEAリスト (嵌合BL〜5BL)")
    return missing


def build_dataset_signature(
    source_bytes: bytes, target_bytes: bytes, pfmea_bytes: bytes
) -> str:
    return hashlib.sha256(source_bytes + target_bytes + pfmea_bytes).hexdigest()


def create_file_change_callback(manager: SessionManager) -> Callable[[], None]:
    """ファイル変更時に古い状態をクリアするコールバック"""

    def _on_change() -> None:
        manager.clear_analysis_result()
        manager.clear_llm_results()
        manager.clear_llm_workflow_info()

    return _on_change


def get_uploaded_files_from_sidebar(
    manager: SessionManager | None = None,
) -> tuple[Any, Any, Any]:
    on_change = create_file_change_callback(manager) if manager else None

    st.sidebar.header("編成表インポート")
    source_file = st.sidebar.file_uploader(
        "流用元編成表（Excel）",
        type=["xlsx"],
        key=SOURCE_FILE_UPLOADER_KEY,
        on_change=on_change,
    )
    target_file = st.sidebar.file_uploader(
        "変更後編成表（Excel）",
        type=["xlsx"],
        key=TARGET_FILE_UPLOADER_KEY,
        on_change=on_change,
    )

    st.sidebar.header("PFMEAファイル")
    pfmea_file = st.sidebar.file_uploader(
        "PFMEA一括ファイル（Excel）",
        type=["xlsx"],
        help="シート名: 嵌合BL / 1BL / 2BL / 3BL / 4BL / 5BL",
        key=PFMEA_FILE_UPLOADER_KEY,
        on_change=on_change,
    )
    return source_file, target_file, pfmea_file


@contextmanager
def _maybe_spinner(label: str) -> Generator[None, None, None]:
    if _has_streamlit_context() and hasattr(st, "spinner"):
        with st.spinner(label):
            yield
    else:
        yield


def load_datasets_with_spinner(
    source_bytes: bytes, target_bytes: bytes, pfmea_bytes: bytes
) -> tuple[Any, Any, Any] | None:
    with _maybe_spinner("ファイルを読み込んでいます..."):
        tasks: list[tuple[str, Callable[[], Any]]] = [
            ("bop_source", lambda: load_bop_master(source_bytes)),
            ("bop_target", lambda: load_bop_master(target_bytes)),
            ("pfmea", lambda: load_pfmea(pfmea_bytes)),
        ]

        wrapper = get_streamlit_task_wrapper()
        try:
            dataset_map = _run_parallel_dataset_tasks(
                tasks,
                wrapper=wrapper,
            )
        except ParallelExecutionError as exc:  # pragma: no cover - UI経由例外
            label = (
                exc.item[0] if isinstance(exc.item, tuple) and exc.item else "dataset"
            )
            cause = exc.__cause__ or exc
            st.error(f"{label} の解析中にエラーが発生しました: {cause}")
            return None
        except Exception as exc:  # pragma: no cover
            st.error(f"ファイル読み込み中に予期しないエラーが発生しました: {exc}")
            return None

        return (
            dataset_map.get("bop_source"),
            dataset_map.get("bop_target"),
            dataset_map.get("pfmea"),
        )


__all__ = [
    "build_dataset_signature",
    "collect_missing_inputs",
    "create_file_change_callback",
    "get_uploaded_files_from_sidebar",
    "load_bop_master",
    "load_datasets_with_spinner",
    "load_pfmea",
]
