"""LangGraph client management for PFMEA Workflow Application."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import jwt
import streamlit as st
from langgraph_sdk import get_sync_client

from .config import settings

logger = logging.getLogger(__name__)


class LangGraphClientError(Exception):
    """Exception raised when LangGraph client operations fail."""

    pass


def _get_internal_token_from_request() -> str | None:
    """Extract internal token from the request's Authorization header or settings.

    Priority:
        1. Token from Authorization header (production and development)
        2. INTERNAL_TOKEN from settings
        (local development ONLY - disabled in production)

    Security:
        In production (ENVIRONMENT=production), fallback to INTERNAL_TOKEN is disabled
        to prevent accidental use of development tokens.

    Returns:
        The JWT token if found, None otherwise.
    """
    # Try to get token from request headers first
    try:
        headers = st.context.headers
        auth_header = headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
    except Exception as e:
        logger.debug("Could not extract token from request headers: %s", e)

    # Fallback to settings for local development ONLY
    # In production, this fallback is disabled for security
    if settings.allow_token_fallback and settings.internal_token:
        logger.debug("Using INTERNAL_TOKEN from settings (development mode)")
        return settings.internal_token
    elif settings.is_production and settings.internal_token:
        logger.warning(
            "INTERNAL_TOKEN is set but ignored in production mode. "
            "Authentication must come from request headers."
        )

    return None


def _build_headers() -> dict[str, str]:
    """Build authentication headers for LangGraph client."""
    headers = {}

    # Get internal token from request headers (passed through by the gateway)
    internal_token = _get_internal_token_from_request()
    if internal_token:
        headers["Authorization"] = f"Bearer {internal_token}"

    if settings.cf_access_client_id:
        headers["CF-Access-Client-Id"] = settings.cf_access_client_id
    if settings.cf_access_client_secret:
        headers["CF-Access-Client-Secret"] = settings.cf_access_client_secret
    return headers


def get_auth_headers() -> dict[str, str]:
    """Get authentication headers from Streamlit context.

    Must be called from synchronous Streamlit context (outside asyncio.run()).
    This allows authentication headers to be captured before entering an async context,
    where st.context.headers may not be available.

    Returns:
        Dictionary of authentication headers.
    """
    return _build_headers()


def get_langgraph_client(headers: dict[str, str] | None = None):
    """Get a fresh LangGraph SDK client.

    Args:
        headers: Pre-built authentication headers. If None, will attempt to
                 build from current context.

    Returns:
        Synchronous LangGraph client instance.

    Raises:
        LangGraphClientError: If client initialization fails.
    """
    try:
        if headers is None:
            headers = _build_headers()

        client = get_sync_client(
            url=settings.backend_url,
            headers=headers if headers else None,
            api_key=settings.langsmith_api_key,
        )
        return client
    except Exception as e:
        logger.error(
            "Failed to initialize synchronous LangGraph client: %s", e, exc_info=True
        )
        raise LangGraphClientError(f"バックエンドへの接続に失敗しました: {e}") from e


def get_tenant_id_from_request() -> str | None:
    """Extract tenant_id from the internal token in the request headers.

    Returns:
        The tenant_id if found and valid, None otherwise.
    """
    token = _get_internal_token_from_request()
    if not token:
        return None

    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        # Verify this is a CADDI internal token
        if decoded.get("iss") == "https://caddi.internal":
            return decoded.get("https://zoolake.jp/claims/tenantId")
        return None
    except jwt.DecodeError as e:
        logger.warning("Failed to decode JWT token: %s", e)
        return None


def start_pfmea_workflow(
    client: Any,
    changes: List[Dict[str, Any]],
    pfmea_context: Dict[str, Any],
    selected_model: str = "gemini-2.5-flash",
) -> tuple[str, str]:
    """Start a PFMEA workflow.

    Args:
        client: Synchronous LangGraph SDK client instance
        changes: List of change records to process
        pfmea_context: PFMEA context data
        selected_model: LLM model to use

    Returns:
        Tuple of (thread_id, run_id) for tracking
    """
    try:
        # Create a new thread
        thread = client.threads.create()
        logger.debug("Thread created: %s, type: %s", thread, type(thread))

        # NOTE: langgraph-sdk のバージョンによって戻り値の型が異なる可能性がある
        thread_id = (
            thread["thread_id"] if isinstance(thread, dict) else thread.thread_id
        )

        # Start the workflow run
        run = client.runs.create(
            thread_id,
            settings.graph_id,
            input={
                "changes": changes,
                "pfmea_context": pfmea_context,
                "selected_model": selected_model,
            },
        )
        logger.debug("Run created: %s, type: %s", run, type(run))

        run_id = run["run_id"] if isinstance(run, dict) else run.run_id

        return thread_id, run_id
    except Exception as e:
        logger.error("Failed to start PFMEA workflow: %s", e, exc_info=True)
        raise LangGraphClientError(f"バックエンドへの接続に失敗しました: {e}") from e


def _parse_workflow_state(state: Any) -> Dict[str, Any]:
    """Parse workflow state from raw response.

    Args:
        state: Raw state response (dict or ThreadState object)

    Returns:
        Dictionary with status and values
    """
    # NOTE: langgraph-sdk のバージョンによって戻り値の型が異なる可能性がある
    # dict 形式と ThreadState オブジェクト形式の両方に対応
    if isinstance(state, dict):
        next_nodes = state.get("next", [])
        values = state.get("values", {})
    else:
        next_nodes = state.next if hasattr(state, "next") else []
        values = state.values if hasattr(state, "values") else {}

    # values が空の場合は running として扱う
    # ワークフローがまだ開始されていない、または初期状態の可能性がある
    if not values:
        status = "running"
    else:
        status = "running" if next_nodes and len(next_nodes) > 0 else "completed"

    logger.info("_parse_workflow_state: calculated status=%s", status)

    return {
        "status": status,
        "values": values,
    }


def get_workflow_state(client: Any, thread_id: str) -> Dict[str, Any]:
    """Get the current state of a workflow.

    Args:
        client: Synchronous LangGraph SDK client instance
        thread_id: The thread ID to check

    Returns:
        Dictionary with status and values
    """
    try:
        state = client.threads.get_state(thread_id)
    except Exception as e:
        logger.warning(
            "get_workflow_state failed for thread %s: %s",
            thread_id,
            e,
        )
        # エラー時はrunningとして継続（ポーリングを継続させる）
        return {"status": "running", "values": {}}

    return _parse_workflow_state(state)


def _parse_workflow_result(state: Any) -> Dict[str, Any]:
    """Parse workflow result from raw state response.

    Args:
        state: Raw state response (dict or ThreadState object)

    Returns:
        Dictionary with workflow results
    """
    # NOTE: langgraph-sdk のバージョンによって戻り値の型が異なる可能性がある
    # dict 形式と ThreadState オブジェクト形式の両方に対応
    if isinstance(state, dict):
        values = state.get("values", {}) or {}
    else:
        values = state.values if hasattr(state, "values") else {}
        values = values or {}

    return {
        "structured_rows": values.get("structured_rows", []),
        "rows_by_change": values.get("rows_by_change", {}),
        "metrics": values.get("metrics", {}),
        "error": values.get("error"),
        "error_code": values.get("error_code"),
        "current_phase": values.get("current_phase", "unknown"),
        "phase_message": values.get("phase_message", ""),
    }


def get_workflow_result(client: Any, thread_id: str) -> Dict[str, Any]:
    """Get the final result of a completed workflow.

    Args:
        client: Synchronous LangGraph SDK client instance
        thread_id: The thread ID

    Returns:
        Dictionary with workflow results
    """
    logger.info(
        "get_workflow_result: fetching result for thread %s", thread_id
    )

    try:
        state = client.threads.get_state(thread_id)
    except Exception as e:
        logger.error(
            "get_workflow_result failed for thread %s: %s",
            thread_id,
            e,
        )
        return {
            "error": f"結果取得に失敗しました: {e}",
            "error_code": "result_fetch_error",
            "structured_rows": [],
            "rows_by_change": {},
            "metrics": {},
            "current_phase": "error",
            "phase_message": "結果取得エラー",
        }

    return _parse_workflow_result(state)


__all__ = [
    "LangGraphClientError",
    "get_auth_headers",
    "get_langgraph_client",
    "get_tenant_id_from_request",
    "start_pfmea_workflow",
    "get_workflow_state",
    "get_workflow_result",
]
