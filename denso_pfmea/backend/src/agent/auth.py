"""Authentication module for extracting tenant_id from internal JWT tokens."""

import jwt
import structlog
from langchain_core.runnables import RunnableConfig
from langgraph_sdk import Auth
from langgraph_sdk.auth import is_studio_user

logger = structlog.stdlib.get_logger(__name__)

# Initialize Auth object for LangSmith
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
    # Get Authorization header (case-insensitive, handle both str and bytes keys)
    auth_header = (
        headers.get("authorization")
        or headers.get("Authorization")
        or headers.get(b"authorization")
        or headers.get(b"Authorization")
        or ""
    )

    # Decode if bytes
    if isinstance(auth_header, bytes):
        auth_header = auth_header.decode("utf-8")

    if not auth_header:
        logger.error(
            "No authorization header provided", available_headers=list(headers.keys())
        )
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
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
    except jwt.DecodeError as e:
        logger.error("Failed to decode JWT token", error=str(e))
        raise Auth.exceptions.HTTPException(status_code=401, detail="Invalid JWT token")

    # Verify this is a CADDI internal token
    if decoded.get("iss") != "https://caddi.internal":
        logger.warning("Invalid issuer", issuer=decoded.get("iss"))
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid token issuer"
        )

    # Extract tenant_id from custom claim
    tenant_id = decoded.get("https://zoolake.jp/claims/tenantId")

    if not tenant_id:
        logger.error("tenant_id not found in token claims")
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Missing tenant_id in token"
        )

    # Extract user info from token claims
    # User ID is in the standard "sub" claim
    user_id = decoded.get("sub", "")
    # Email is in a custom claim namespace
    user_email = decoded.get("https://zoolake.jp/claims/email", "")

    logger.debug("Successfully authenticated", tenant_id=tenant_id, user_id=user_id)

    # Return user info that will be available in config["configurable"]["langgraph_auth_user"]
    return {
        "identity": tenant_id,  # Required field for LangGraph auth
        "tenant_id": tenant_id,  # Custom field for our application
        "user_id": user_id,  # User identifier (sub claim, e.g., "auth0|xxx")
        "user_email": user_email,  # User email from custom claim
        "internal_token": token,  # Original token to pass to ISP for authentication
    }


def get_tenant_id_from_config(config: RunnableConfig) -> str | None:
    """Extract tenant_id from LangGraph config.

    This is a helper function to extract tenant_id from the config object
    that is passed to workflow nodes.

    Args:
        config: LangGraph RunnableConfig containing auth user info

    Returns:
        tenant_id if available, None otherwise

    Example:
        >>> def my_node(state: MyState, config: RunnableConfig) -> dict:
        ...     tenant_id = get_tenant_id_from_config(config)
        ...     if tenant_id:
        ...         logger.info(f"Processing for tenant: {tenant_id}")
        ...     return {"error": None}
    """
    try:
        auth_user = config.get("configurable", {}).get("langgraph_auth_user", {})
        tenant_id = auth_user.get("tenant_id")

        if tenant_id:
            logger.debug("Retrieved tenant_id from config", tenant_id=tenant_id)
        else:
            logger.warning("tenant_id not found in config")

        return tenant_id

    except Exception as e:
        logger.error("Error extracting tenant_id from config", error=str(e))
        return None


# ========== Authorization Handlers ==========
# These handlers enforce tenant isolation for LangGraph resources


@auth.on.threads.create
async def authorize_thread_create(
    ctx: Auth.types.AuthContext, value: Auth.types.on.threads.create.value
) -> None:
    """Add tenant_id and user info to thread metadata on creation.

    This ensures every thread is tagged with its owner's tenant_id and user info,
    enabling tenant-based filtering, access control, and audit trail.

    Note: We mutate value["metadata"] directly as required by LangGraph.
    """
    # Skip authorization for Studio users (development/debugging)
    if is_studio_user(ctx.user):
        logger.debug("Skipping thread create authorization for Studio user")
        return

    tenant_id = ctx.user.get("tenant_id")
    if not tenant_id:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing tenant_id")

    # Extract user info
    user_id = ctx.user.get("user_id", "")
    user_email = ctx.user.get("user_email", "")

    # Mutate metadata directly (required by LangGraph)
    metadata = value.setdefault("metadata", {})
    if metadata is None:
        value["metadata"] = metadata = {}
    metadata["tenant_id"] = tenant_id
    metadata["created_by"] = {
        "user_id": user_id,
        "user_email": user_email,
    }

    logger.debug("Creating thread", tenant_id=tenant_id, user_id=user_id)


@auth.on.threads.read
async def authorize_thread_read(
    ctx: Auth.types.AuthContext, value: Auth.types.on.threads.read.value
) -> Auth.types.FilterType:
    """Filter thread reads to only allow access to user's own tenant's threads.

    Returns a filter that restricts access to threads with matching tenant_id.
    This approach works even when metadata is not included in the value parameter.
    """
    # Skip authorization for Studio users (development/debugging)
    if is_studio_user(ctx.user):
        logger.debug("Skipping thread read authorization for Studio user")
        return {}

    user_tenant = ctx.user.get("tenant_id")
    thread_id = value.get("thread_id")

    logger.debug("authorize_thread_read", thread_id=thread_id, user_tenant=user_tenant)

    if not user_tenant:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing tenant_id")

    # Return a filter to restrict access to threads with matching tenant_id
    # The filter key should match the metadata field name directly (not nested)
    # LangGraph Platform applies this filter at the database level
    return {"tenant_id": user_tenant}


@auth.on.threads.search
async def filter_threads_by_tenant(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.search.value,  # noqa: ARG001
) -> Auth.types.FilterType:
    """Filter threads search to only return current tenant's threads.

    This filter is automatically applied to all thread search operations.
    The filter key should match the metadata field name directly (not nested).
    LangGraph Platform applies this as metadata.tenant_id filter at the database level.
    """
    # Skip authorization for Studio users (development/debugging)
    if is_studio_user(ctx.user):
        logger.debug("Skipping thread search authorization for Studio user")
        return {}

    tenant_id = ctx.user.get("tenant_id")
    if not tenant_id:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing tenant_id")

    logger.debug("Filtering threads for tenant", tenant_id=tenant_id)
    return {"tenant_id": tenant_id}


# ========== Runs Authorization Handler ==========
# Runs are scoped to their parent thread for access control.
# Thread access is already verified by @auth.on.threads.read before create_run is called,
# so we just need to ensure the run metadata includes tenant info for future access control.


@auth.on.threads.create_run
async def authorize_create_run(
    ctx: Auth.types.AuthContext, value: Auth.types.on.threads.create_run.value
) -> None:
    """Add tenant_id to run metadata.

    Thread-level access control is already enforced by threads.read handler.
    This handler ensures run metadata includes tenant info for consistency.
    We mutate value["metadata"] directly (side effect) and return None
    since no filter is needed for run creation.
    """
    # Skip authorization for Studio users (development/debugging)
    if is_studio_user(ctx.user):
        logger.debug("Skipping run create authorization for Studio user")
        return

    tenant_id = ctx.user.get("tenant_id")
    user_id = ctx.user.get("user_id", "")

    # Mutate metadata directly (required by LangGraph)
    metadata = value.setdefault("metadata", {})
    if metadata is None:
        value["metadata"] = metadata = {}
    metadata["tenant_id"] = tenant_id
    metadata["created_by"] = user_id

    logger.debug("Creating run", tenant_id=tenant_id, user_id=user_id)
    # Return None - no filter needed, thread access is already verified


# ========== Helper Functions ==========


def _is_production_environment() -> bool:
    """Check if running in production environment."""
    import os

    env = os.environ.get("ENVIRONMENT", "development").lower()
    return env == "production"


def get_internal_token_from_config(config: RunnableConfig) -> str | None:
    """Extract internal token from LangGraph config or environment variable.

    This is a helper function to extract the original JWT token from the config object
    that is passed to workflow nodes. The token can be used to authenticate with ISP.

    Priority:
        1. Token from config (passed via Authorization header)
        2. INTERNAL_TOKEN environment variable (for local development ONLY)

    Security:
        In production (ENVIRONMENT=production), fallback to INTERNAL_TOKEN is disabled
        to prevent accidental use of development tokens.

    Args:
        config: LangGraph RunnableConfig containing auth user info

    Returns:
        internal token if available, None otherwise

    Example:
        >>> def my_node(state: MyState, config: RunnableConfig) -> dict:
        ...     internal_token = get_internal_token_from_config(config)
        ...     if internal_token:
        ...         isp_manager.set_internal_token(internal_token)
        ...     return {"error": None}
    """
    import os

    try:
        auth_user = config.get("configurable", {}).get("langgraph_auth_user", {})
        internal_token = auth_user.get("internal_token")

        if internal_token:
            logger.debug("Retrieved internal token from config")
            return internal_token

        # Fallback to environment variable for local development ONLY
        # In production, this fallback is disabled for security
        env_token = os.environ.get("INTERNAL_TOKEN")
        if env_token:
            if _is_production_environment():
                logger.warning(
                    "INTERNAL_TOKEN is set but ignored in production mode. "
                    "Authentication must come from request headers."
                )
            else:
                logger.debug(
                    "Retrieved internal token from INTERNAL_TOKEN environment variable (development mode)"
                )
                return env_token

        logger.warning("internal token not found in config or environment")
        return None

    except Exception as e:
        logger.error(f"Error extracting internal token from config: {e}")
        return None
