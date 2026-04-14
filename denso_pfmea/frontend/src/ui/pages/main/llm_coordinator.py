"""Coordinator responsible for executing the full LLM workflow via Backend."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any

from src.client import get_auth_headers
from src.common.perf import record_event
from src.services.pfmea_context import PfmeaContext

from .constants import (
    DEFAULT_VERTEX_MODEL,
)
from .llm_progress_tracker import (
    LLM_PROGRESS_BASE,
)

MAX_POLL_TIMEOUT_SECONDS = 600  # ポーリングタイムアウト（10分）

logger = logging.getLogger(__name__)


def _serialize_change(change: Any) -> dict[str, Any]:
    """Serialize a change record to a dictionary for API transmission."""
    if hasattr(change, "to_dict"):
        return change.to_dict()
    if hasattr(change, "__dict__"):
        return {k: v for k, v in change.__dict__.items() if not k.startswith("_")}
    return dict(change) if isinstance(change, Mapping) else {}


def _calculate_progress(current_phase: str) -> int:
    """Calculate progress value based on current phase."""
    if current_phase == "mapping":
        return LLM_PROGRESS_BASE + 10
    elif current_phase == "assessment_complete":
        return LLM_PROGRESS_BASE + 50
    elif current_phase == "rating_complete":
        return LLM_PROGRESS_BASE + 80
    elif current_phase == "complete":
        return 100
    elif current_phase == "error":
        return LLM_PROGRESS_BASE
    else:
        return LLM_PROGRESS_BASE + 5


def _serialize_pfmea_context(
    pfmea_context: Mapping[str, PfmeaContext | None],
) -> dict[str, Any]:
    """Serialize PFMEA context to a dictionary for API transmission.

    NOTE: DataFrame は JSON シリアライズできないため、List[Dict] に変換する。
    Backend の _reconstruct_pfmea_context で pd.DataFrame に復元される。
    """
    result: dict[str, Any] = {}
    for change_id, ctx in pfmea_context.items():
        if ctx is None:
            result[change_id] = None
        else:
            # DataFrame を JSON シリアライズ可能な形式に変換
            data_serialized = None
            if ctx.data is not None:
                data_serialized = ctx.data.to_dict(orient="records")

            # summaries も同様にシリアライズ
            summaries_serialized: dict[str, Any] = {}
            for key, summary in ctx.summaries.items():
                if hasattr(summary, "to_dict"):
                    summaries_serialized[key] = summary.to_dict()
                elif hasattr(summary, "__dict__"):
                    summaries_serialized[key] = {
                        k: v
                        for k, v in summary.__dict__.items()
                        if not k.startswith("_")
                    }
                elif isinstance(summary, Mapping):
                    summaries_serialized[key] = dict(summary)
                else:
                    summaries_serialized[key] = str(summary)

            result[change_id] = {
                "block": ctx.block,
                "data": data_serialized,
                "summaries": summaries_serialized,
            }
    return result


def _process_workflow_result(
    session_manager: Any,
    result: dict[str, Any],
) -> tuple[bool, str | None]:
    """Process workflow result and store in session.

    Args:
        session_manager: Session manager instance
        result: Workflow result dictionary

    Returns:
        Tuple of (success, error_message)
    """
    # Check for errors
    if result.get("error"):
        error_message = result.get("error", "バックエンドでエラーが発生しました")
        error_code = result.get("error_code")
        record_event(
            "backend_workflow_error",
            metadata={
                "phase": "llm",
                "error": error_message,
                "error_code": error_code,
            },
        )
        return False, error_message

    # Process results
    structured_rows = result.get("structured_rows", [])
    rows_by_change = result.get("rows_by_change", {})
    metrics = result.get("metrics", {})

    # Store results in session
    session_manager.set_llm_structured_rows(rows_by_change, structured_rows)
    session_manager.set_llm_metrics(metrics)

    return True, None


def start_workflow(
    auth_headers: dict[str, str],
    serialized_changes: list[dict[str, Any]],
    serialized_context: dict[str, Any],
    selected_model: str,
) -> tuple[str, str]:
    """Start workflow synchronously and return thread_id, run_id.

    No polling - caller is responsible for checking status.
    """
    from src.client import get_langgraph_client, start_pfmea_workflow
    from src.common.perf import time_block

    client = get_langgraph_client(headers=auth_headers)

    with time_block(
        "start_backend_workflow", metadata={"phase": "llm", "model": selected_model}
    ):
        thread_id, run_id = start_pfmea_workflow(
            client,
            serialized_changes,
            serialized_context,
            selected_model,
        )

    logger.info("Workflow started: thread_id=%s, run_id=%s", thread_id, run_id)
    return thread_id, run_id


def start_llm_workflow(
    session_manager: Any,
    actionable_changes: Sequence[Any],
    pfmea_context: Mapping[str, PfmeaContext | None],
    *,
    env: Mapping[str, str],
    selected_model: str | None = None,
) -> str | None:
    """Start LLM workflow synchronously.

    Returns thread_id on success, None on error or no changes.
    Stores thread_id in session_state for polling.

    Args:
        session_manager: Session manager instance
        actionable_changes: List of changes to process
        pfmea_context: PFMEA context mapping
        env: Environment variables
        selected_model: Optional model override

    Returns:
        thread_id if started, None otherwise
    """
    # Serialize data
    changes = list(actionable_changes)
    total_requests = len(changes)

    if total_requests == 0:
        return None

    serialized_changes = [_serialize_change(c) for c in changes]
    serialized_context = _serialize_pfmea_context(pfmea_context)

    # Get auth headers from Streamlit context
    auth_headers = get_auth_headers()

    # Determine model
    if selected_model is None:
        preferred_getter = getattr(
            session_manager, "get_preferred_vertex_model", lambda: None
        )
        preferred_model = preferred_getter()
        current_model = getattr(
            session_manager, "get_current_vertex_model", lambda: None
        )()
        selected_model = preferred_model or current_model or DEFAULT_VERTEX_MODEL

    # Clear previous results
    session_manager.clear_llm_results()

    try:
        thread_id, run_id = start_workflow(
            auth_headers,
            serialized_changes,
            serialized_context,
            selected_model,
        )
    except Exception as e:
        logger.exception("Failed to start workflow")
        record_event(
            "backend_connection_error",
            metadata={"phase": "llm", "error": str(e)},
        )
        return None

    # Store workflow info for frontend polling
    session_manager.set_llm_workflow_info(
        thread_id=thread_id,
        run_id=run_id,
        total_requests=total_requests,
        started_at=time.time(),
    )

    return thread_id


__all__ = [
    "MAX_POLL_TIMEOUT_SECONDS",
    "_calculate_progress",
    "_process_workflow_result",
    "start_llm_workflow",
]
