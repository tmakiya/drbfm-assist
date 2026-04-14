"""Authentication module for extracting tenant_id from internal JWT tokens."""

from __future__ import annotations

import logging
import os
from typing import Any

import jwt
from langchain_core.runnables import RunnableConfig
from langgraph_sdk import Auth
from langgraph_sdk.auth import is_studio_user

logger = logging.getLogger(__name__)

# JWT Claim keys
CLAIM_TENANT_ID = "https://zoolake.jp/claims/tenantId"
CLAIM_EMAIL = "https://zoolake.jp/claims/email"
INTERNAL_ISSUER = "https://caddi.internal"


def _get_header_value(headers: dict, key: str) -> str | None:
    """Get header value, handling both string and bytes keys case-insensitively.

    Args:
        headers: Request headers dictionary
        key: Header key to search for

    Returns:
        Header value as string if found, None otherwise
    """
    key_lower = key.lower()
    for header_key, value in headers.items():
        # Normalize key to string
        if isinstance(header_key, bytes):
            header_key = header_key.decode("utf-8")
        if header_key.lower() == key_lower:
            # Normalize value to string
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value
    return None


def _decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode JWT token without signature verification.

    Args:
        token: JWT token string

    Returns:
        Decoded token claims if successful, None otherwise
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.DecodeError as e:
        logger.error(f"Failed to decode JWT token: {e}")
        return None


# Initialize Auth object for LangGraph Platform
auth = Auth()


@auth.authenticate
async def authenticate(headers: dict) -> Auth.types.MinimalUserDict:
    """Authenticate request and extract user information from headers.

    This function is called by LangGraph Platform to authenticate incoming requests.
    It extracts the JWT token from the Authorization header and validates it.

    Args:
        headers: Request headers dictionary

    Returns:
        MinimalUserDict containing user identity and tenant_id

    Raises:
        Auth.exceptions.HTTPException: If authentication fails
    """
    auth_header = _get_header_value(headers, "authorization") or ""

    if not auth_header:
        logger.error("No authorization header provided")
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="No authorization header"
        )

    # Extract token from "Bearer <token>" format
    if not auth_header.startswith("Bearer "):
        logger.error("Invalid authorization header format")
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Decode JWT without signature verification
    # (signature is already verified by the gateway)
    decoded = _decode_jwt(token)
    if decoded is None:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Invalid JWT token")

    # Verify this is a CADDI internal token
    if decoded.get("iss") != INTERNAL_ISSUER:
        logger.warning(f"Invalid issuer: {decoded.get('iss')}")
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid token issuer"
        )

    # Extract tenant_id from custom claim
    tenant_id = decoded.get(CLAIM_TENANT_ID)

    if not tenant_id:
        logger.error("tenant_id not found in token claims")
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Missing tenant_id in token"
        )

    # Extract user info from token claims
    user_id = decoded.get("sub", "")
    user_email = decoded.get(CLAIM_EMAIL, "")

    logger.debug(
        f"Successfully authenticated: tenant_id={tenant_id}, user_id={user_id}"
    )

    # Return user info that will be available in config["configurable"]["langgraph_auth_user"]
    return {
        "identity": tenant_id,  # Required field for LangGraph auth
        "tenant_id": tenant_id,  # Custom field for our application
        "user_id": user_id,  # User identifier (sub claim)
        "user_email": user_email,  # User email from custom claim
        "internal_token": token,  # Original token to pass to ISP for authentication
    }


# ========== Helper Functions ==========


def _is_development_environment() -> bool:
    """Check if running in development environment.

    Development environment is identified by the presence of INTERNAL_TOKEN env var.
    """
    return os.environ.get("INTERNAL_TOKEN") is not None


def _decode_tenant_id_from_token(token: str) -> str | None:
    """Decode tenant_id from JWT token.

    Args:
        token: JWT token string

    Returns:
        tenant_id if found, None otherwise
    """
    decoded = _decode_jwt(token)
    if decoded is None:
        return None
    return decoded.get(CLAIM_TENANT_ID)


def get_tenant_id_from_config(config: RunnableConfig) -> str | None:
    """Extract tenant_id from LangGraph config.

    Priority:
        1. tenant_id from config (extracted from JWT by auth.py authenticate)
        2. Decode from INTERNAL_TOKEN environment variable (for development)

    Args:
        config: LangGraph RunnableConfig containing auth user info

    Returns:
        tenant_id if available, None otherwise
    """
    try:
        auth_user = config.get("configurable", {}).get("langgraph_auth_user", {})
        tenant_id = auth_user.get("tenant_id")

        if tenant_id:
            logger.debug("Retrieved tenant_id from config")
            return tenant_id

        # Fallback: decode from INTERNAL_TOKEN env var for development
        env_token = os.environ.get("INTERNAL_TOKEN")
        if env_token:
            tenant_id = _decode_tenant_id_from_token(env_token)
            if tenant_id:
                logger.debug("Retrieved tenant_id from INTERNAL_TOKEN env")
                return tenant_id

        logger.warning("tenant_id not found in config or INTERNAL_TOKEN")
        return None

    except Exception as e:
        logger.error(f"Error extracting tenant_id from config: {e}")
        return None


def get_internal_token_from_config(config: RunnableConfig) -> str | None:
    """Extract internal token from LangGraph config or environment variable.

    Priority:
        1. Token from config (passed via Authorization header)
        2. INTERNAL_TOKEN environment variable (for development)

    Args:
        config: LangGraph RunnableConfig containing auth user info

    Returns:
        internal token if available, None otherwise
    """
    try:
        auth_user = config.get("configurable", {}).get("langgraph_auth_user", {})
        internal_token = auth_user.get("internal_token")

        if internal_token:
            logger.debug("Retrieved internal token from config")
            return internal_token

        # Fallback to environment variable for development
        env_token = os.environ.get("INTERNAL_TOKEN")
        if env_token:
            logger.debug("Retrieved internal token from INTERNAL_TOKEN env var")
            return env_token

        logger.warning("internal token not found in config or environment")
        return None

    except Exception as e:
        logger.error(f"Error extracting internal token from config: {e}")
        return None


# ========== Authorization Handlers ==========


@auth.on.threads.create
async def authorize_thread_create(
    ctx: Auth.types.AuthContext, value: Auth.types.on.threads.create.value
) -> None:
    """Add tenant_id and user info to thread metadata on creation."""
    if is_studio_user(ctx.user):
        logger.debug("Skipping authorization for Studio user")
        return

    tenant_id = ctx.user.get("tenant_id")
    if not tenant_id:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing tenant_id")

    user_id = ctx.user.get("user_id", "")
    user_email = ctx.user.get("user_email", "")

    metadata = value.setdefault("metadata", {})
    if metadata is None:
        value["metadata"] = metadata = {}
    metadata["tenant_id"] = tenant_id
    metadata["created_by"] = {"user_id": user_id, "user_email": user_email}

    logger.debug("Creating thread")


@auth.on.threads.read
async def authorize_thread_read(
    ctx: Auth.types.AuthContext, value: Auth.types.on.threads.read.value
) -> Auth.types.FilterType:
    """Filter thread reads to only allow access to user's own tenant's threads."""
    if is_studio_user(ctx.user):
        return {}

    user_tenant = ctx.user.get("tenant_id")
    if not user_tenant:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing tenant_id")

    return {"tenant_id": user_tenant}


@auth.on.threads.search
async def filter_threads_by_tenant(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.search.value,  # noqa: ARG001
) -> Auth.types.FilterType:
    """Filter threads search to only return current tenant's threads."""
    if is_studio_user(ctx.user):
        return {}

    tenant_id = ctx.user.get("tenant_id")
    if not tenant_id:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing tenant_id")

    return {"tenant_id": tenant_id}


@auth.on.threads.create_run
async def authorize_create_run(
    ctx: Auth.types.AuthContext, value: Auth.types.on.threads.create_run.value
) -> None:
    """Add tenant_id to run metadata."""
    if is_studio_user(ctx.user):
        return

    tenant_id = ctx.user.get("tenant_id")
    user_id = ctx.user.get("user_id", "")

    metadata = value.setdefault("metadata", {})
    if metadata is None:
        value["metadata"] = metadata = {}
    metadata["tenant_id"] = tenant_id
    metadata["created_by"] = user_id

    logger.debug("Creating run")
