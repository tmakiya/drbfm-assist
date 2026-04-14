"""Async ISP client for backend search operations."""

from __future__ import annotations

import logging
import os
from types import TracebackType
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ISPClientError(Exception):
    """Base exception for ISP client errors."""

    pass


class ISPSearchError(ISPClientError):
    """Exception raised when ISP search fails."""

    def __init__(
        self, message: str, status_code: int | None = None, detail: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class AsyncISPClient:
    """Async client for ISP search operations.

    This client is designed for search-only operations in the LangGraph workflow.
    It uses httpx for async HTTP requests with connection pooling.

    Usage:
        async with AsyncISPClient(base_url, tenant_id, internal_token) as client:
            result = await client.search(index_alias, query)
    """

    def __init__(
        self,
        base_url: str,
        tenant_id: str | None = None,
        internal_token: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize ISP client.

        Args:
            base_url: ISP API base URL
            tenant_id: Tenant ID for multi-tenancy
            internal_token: Internal token for authentication (production)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.internal_token = internal_token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AsyncISPClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager and close client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication.

        Headers are built fresh for each request to ensure authentication
        tokens are not inadvertently reused across different request contexts.
        """
        headers = {"Content-Type": "application/json"}
        if self.internal_token:
            # Production: Use Internal Token (Bearer)
            headers["Authorization"] = f"Bearer {self.internal_token}"
        elif self.tenant_id:
            # Development: Use tenant ID header
            headers["x-caddi-tenant-id"] = self.tenant_id
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def search(
        self,
        index_alias: str,
        query: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute search query against ISP.

        Args:
            index_alias: ISP index alias name (e.g., 'suzuki-technology-trends_tenant-id')
            query: Full ISP search request body

        Returns:
            ISP search response

        Raises:
            ISPSearchError: If the search request fails
        """
        url = f"{self.base_url}/{index_alias}/_search"

        logger.debug("ISP search request")

        client = await self._get_client()
        try:
            response = await client.post(
                url,
                json=query,
                headers=self._build_headers(),
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"ISP search failed: status={e.response.status_code}")
            raise ISPSearchError(
                f"ISP search failed with status {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"ISP search timeout: url={url}, timeout={self.timeout}s")
            raise ISPSearchError(f"ISP search timeout after {self.timeout}s") from e
        except httpx.RequestError as e:
            logger.error(f"ISP search request error: url={url}, error={e}")
            raise ISPSearchError(f"ISP search request failed: {e}") from e

    async def health_check(self) -> dict[str, Any]:
        """Check ISP API health status.

        Returns:
            Health check response

        Raises:
            ISPClientError: If the health check fails
        """
        url = f"{self.base_url}/_health"
        client = await self._get_client()
        try:
            response = await client.get(url, headers=self._build_headers())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"ISP health check failed: status={e.response.status_code}")
            raise ISPClientError(
                f"Health check failed: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error(f"ISP health check request error: {e}")
            raise ISPClientError(f"Health check request failed: {e}") from e

    async def close(self) -> None:
        """Close the HTTP client explicitly."""
        if self._client:
            await self._client.aclose()
            self._client = None


def create_isp_client(
    tenant_id: str | None = None,
    internal_token: str | None = None,
) -> AsyncISPClient:
    """Create ISP client.

    Environment variables:
        ISP_URL: ISP base URL (default: http://localhost:50080)

    Args:
        tenant_id: Tenant ID (required, extracted from JWT)
        internal_token: Internal token for authentication (required)

    Returns:
        Configured AsyncISPClient instance
    """
    base_url = os.getenv("ISP_URL", "http://localhost:50080")

    logger.debug("Creating ISP client")

    return AsyncISPClient(
        base_url=base_url,
        tenant_id=tenant_id,
        internal_token=internal_token,
    )


def get_index_alias(
    base_name: str = "suzuki-technology-trends",
    tenant_id: str | None = None,
) -> str:
    """Get tenant-specific index alias.

    Args:
        base_name: Base index name
        tenant_id: Tenant ID to append

    Returns:
        Full index alias name (e.g., 'suzuki-technology-trends_tenant-id')
    """
    if tenant_id:
        return f"{base_name}_{tenant_id}"
    return base_name
