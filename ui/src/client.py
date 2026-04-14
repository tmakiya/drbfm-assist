"""LangGraph client management for DRBFM Workflow Application."""

import jwt
import streamlit as st
from langgraph_sdk import get_client
from loguru import logger

from .config import settings


class LangGraphClientError(Exception):
    """Exception raised when LangGraph client operations fail."""

    pass


def _get_internal_token_from_request() -> str | None:
    """Extract internal token from the request's Authorization header or settings.

    Priority:
        1. Token from Authorization header (production and development)
        2. INTERNAL_TOKEN from settings (local development ONLY - disabled in production)

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
        logger.bind(error=str(e)).debug("Could not extract token from request headers")

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


def get_langgraph_client():
    """Get a fresh LangGraph SDK client.

    Note: We intentionally do NOT cache the client with @st.cache_resource because
    the underlying httpx.AsyncClient gets bound to a specific event loop. When using
    asyncio.run() in Streamlit (which creates a new event loop each time), a cached
    client would fail with "Event loop is closed" errors on subsequent calls.

    Returns:
        LangGraph client instance.

    Raises:
        LangGraphClientError: If client initialization fails.
    """
    try:
        headers = _build_headers()

        client = get_client(
            url=settings.backend_url,
            headers=headers if headers else None,
            api_key=settings.langsmith_api_key,
        )
        return client
    except Exception as e:
        logger.bind(backend_url=settings.backend_url, error=str(e)).error(
            "Failed to initialize LangGraph client"
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
        logger.bind(error=str(e)).warning("Failed to decode JWT token")
        return None
