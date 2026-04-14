from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import (
    Any,
)

try:  # pragma: no cover - Streamlitは実行環境に依存する
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from src.services.change_pipeline.models import ComparisonMode
from src.services.runtime_session import RuntimeSession
from src.ui.session_keys import SessionKeys

from .stores import (
    AnalysisStore,
    DatasetStore,
    ThemeStore,
)


@dataclass
class SessionManager(RuntimeSession):
    """Central session state manager using type-safe SessionKeys.

    All session state access uses SessionKeys enum for type safety.
    No legacy class attributes - use SessionKeys directly.
    """

    storage: MutableMapping[str, Any]

    def __post_init__(self) -> None:
        RuntimeSession.__init__(self, self.storage)
        self._datasets = DatasetStore(self.storage)
        self._analysis = AnalysisStore(self.storage)
        self._theme = ThemeStore(self.storage)

    @staticmethod
    def _normalize_mode(mode: object) -> ComparisonMode:
        if isinstance(mode, ComparisonMode):
            return mode
        if isinstance(mode, str):
            try:
                return ComparisonMode(mode)
            except ValueError:
                return ComparisonMode.SINGLE_VARIANT
        return ComparisonMode.SINGLE_VARIANT

    # Dataset orchestration ---------------------------------------------------------
    def dataset_changed(self, signature: str) -> bool:
        changed = self._datasets.mark_if_changed(signature)
        if changed:
            self.clear_llm_results()
            self._analysis.clear()
            self.clear_pfmea_mapping_cache()
            self.set_analysis_running(False)
            self.storage[SessionKeys.ANALYSIS_REQUEST] = False
            self.storage[SessionKeys.LLM_REQUEST] = False
        return changed

    def get_dataset_signature(self) -> str | None:
        return self._datasets.get()

    def get_comparison_mode(self) -> ComparisonMode:
        value = self.storage.get(SessionKeys.COMPARISON_MODE)
        return self._normalize_mode(value)

    def set_comparison_mode(self, mode: ComparisonMode) -> None:
        normalized = self._normalize_mode(mode)
        self.storage[SessionKeys.COMPARISON_MODE] = normalized.value

    def clear_llm_results(self) -> None:
        """Clear all LLM-related data: structured rows and metrics."""
        self.clear_llm_structured_rows()
        self.storage.pop(SessionKeys.LLM_METRICS, None)

    def set_llm_structured_rows(
        self,
        rows_by_change: Mapping[str, Sequence[Mapping[str, str]]],
        all_rows: Sequence[Mapping[str, str]] | None = None,  # 非推奨、無視
    ) -> None:
        """Store LLM structured rows (by_change only, all_rows computed on read)."""
        normalized_by_change: dict[str, list[dict[str, str]]] = {}
        for change_id, rows in rows_by_change.items():
            normalized_by_change[str(change_id)] = [
                {
                    key: ("" if value is None else str(value))
                    for key, value in row.items()
                }
                for row in rows
            ]
        # by_change のみ保存（all_rows は get 時に動的計算）
        self.storage[SessionKeys.LLM_STRUCTURED_ROWS] = normalized_by_change

    def get_llm_structured_rows(self) -> dict[str, Any]:
        """Get LLM structured rows (all_rows computed from by_change)."""
        by_change = self.storage.get(SessionKeys.LLM_STRUCTURED_ROWS, {})
        if not isinstance(by_change, dict):
            return {"by_change": {}, "all_rows": []}
        # all_rows を by_change から動的に計算
        all_rows: list[dict[str, str]] = []
        for rows in by_change.values():
            if isinstance(rows, list):
                all_rows.extend(rows)
        return {"by_change": by_change, "all_rows": all_rows}

    def set_llm_metrics(self, metrics: Mapping[str, Any]) -> None:
        self.storage[SessionKeys.LLM_METRICS] = dict(metrics)

    def get_llm_metrics(self) -> dict[str, Any]:
        payload = self.storage.get(SessionKeys.LLM_METRICS, {})
        if isinstance(payload, dict):
            return dict(payload)
        return {}

    def clear_llm_structured_rows(self) -> None:
        self.storage.pop(SessionKeys.LLM_STRUCTURED_ROWS, None)

    # LLM workflow info for frontend polling ----------------------------------
    def set_llm_workflow_info(
        self,
        *,
        thread_id: str,
        run_id: str,
        total_requests: int,
        started_at: float,
    ) -> None:
        """Store LLM workflow info for frontend polling."""
        self.storage[SessionKeys.LLM_WORKFLOW_INFO] = {
            "thread_id": thread_id,
            "run_id": run_id,
            "total_requests": total_requests,
            "started_at": started_at,
        }

    def get_llm_workflow_info(self) -> dict[str, Any] | None:
        """Get LLM workflow info for polling."""
        info = self.storage.get(SessionKeys.LLM_WORKFLOW_INFO)
        if isinstance(info, dict):
            return info
        return None

    def clear_llm_workflow_info(self) -> None:
        """Clear LLM workflow info after completion."""
        self.storage.pop(SessionKeys.LLM_WORKFLOW_INFO, None)

    def cleanup_after_workflow(self) -> None:
        """ワークフロー完了後の不要データをクリア"""
        self.clear_llm_workflow_info()

    # Analysis state ----------------------------------------------------------------
    def get_analysis_result(self) -> Any | None:
        return self._analysis.result()

    def set_analysis_result(self, result: Any) -> None:
        self._analysis.set_result(result)

    def clear_analysis_result(self) -> None:
        self._analysis.clear()

    def update_analysis_selection(self, selection: tuple[str, str]) -> None:
        self._analysis.set_selection(selection)

    def get_analysis_selection(self) -> tuple[str, str] | None:
        return self._analysis.selection()

    def get_analysis_status(self) -> dict[str, Any] | None:
        return self._analysis.status()

    def set_analysis_status(
        self,
        *,
        label: str,
        value: int,
        kind: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self._analysis.set_status(label=label, value=value, kind=kind, details=details)

    def clear_analysis_status(self) -> None:
        self._analysis.clear_status()

    def set_analysis_running(self, active: bool) -> None:
        if active:
            self.storage[SessionKeys.ANALYSIS_RUNNING] = True
        else:
            self.storage[SessionKeys.ANALYSIS_RUNNING] = False

    def is_analysis_running(self) -> bool:
        return bool(self.storage.get(SessionKeys.ANALYSIS_RUNNING, False))

    def request_analysis_run(self) -> None:
        self.storage[SessionKeys.ANALYSIS_REQUEST] = True
        self.set_analysis_running(True)

    def consume_analysis_request(self) -> bool:
        if bool(self.storage.get(SessionKeys.ANALYSIS_REQUEST, False)):
            self.storage[SessionKeys.ANALYSIS_REQUEST] = False
            return True
        return False

    def request_llm_run(self) -> None:
        self.storage[SessionKeys.LLM_REQUEST] = True
        self.set_analysis_running(True)

    def consume_llm_request(self) -> bool:
        if bool(self.storage.get(SessionKeys.LLM_REQUEST, False)):
            self.storage[SessionKeys.LLM_REQUEST] = False
            return True
        return False

    # Theme management ---------------------------------------------------------------
    def get_theme_base(self) -> str:
        """Get current theme base ('light' or 'dark')."""
        return self._theme.get_base()

    def set_theme_base(self, theme: str) -> None:
        """Set theme base ('light' or 'dark')."""
        self._theme.set_base(theme)

    def get_theme_detection_state(self) -> str:
        """Get theme detection state ('pending', 'active', 'done', 'failed')."""
        return self._theme.get_detection_state()

    def set_theme_detection_state(self, state: str) -> None:
        """Set theme detection state."""
        self._theme.set_detection_state(state)

    def is_theme_configured(self) -> bool:
        """Check if theme has been configured."""
        return self._theme.is_configured()

    def set_theme_configured(self, configured: bool) -> None:
        """Mark theme as configured."""
        self._theme.set_configured(configured)

    def get_theme_applied_base(self) -> str | None:
        """Get last applied base theme."""
        return self._theme.get_applied_base()

    def set_theme_applied_base(self, theme: str) -> None:
        """Set last applied base theme."""
        self._theme.set_applied_base(theme)

    def get_theme_detection_attempts(self) -> int:
        """Get number of detection attempts."""
        return self._theme.get_detection_attempts()

    def increment_theme_detection_attempts(self) -> int:
        """Increment detection attempts."""
        return self._theme.increment_detection_attempts()

    def reset_theme_detection(self) -> None:
        """Reset theme detection state."""
        self._theme.reset_detection()

    def clear_theme_state(self) -> None:
        """Clear all theme state."""
        self._theme.clear()


def get_session_manager(
    storage: MutableMapping[str, Any] | None = None,
) -> SessionManager:
    if storage is None:
        if st is None:  # pragma: no cover - CLI実行向け
            raise RuntimeError(
                "Streamlit is not available; storage must be provided explicitly."
            )
        storage = st.session_state  # type: ignore[assignment]

    # Type narrowing: storage is not None at this point
    assert storage is not None
    return SessionManager(storage=storage)
