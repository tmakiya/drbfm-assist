"""ISP (Interactive Search Platform) client for data ingestion."""

import os
from typing import Any

import requests
from loguru import logger

from ..m2m_token_issuer import create_m2m_token_issuer_client_from_env


class ISPClient:
    """Client for ISP index and document operations."""

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        tenant_id: str | None = None,
        timeout: int = 30,
        internal_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.timeout = timeout
        self.internal_token = internal_token
        self.session = requests.Session()
        self.session.trust_env = False

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.internal_token:
            # When using Internal Token, the gateway extracts tenant_id from the token
            # and adds x-caddi-tenant-id header, so we don't need to set it here
            headers["Authorization"] = f"Bearer {self.internal_token}"
        elif self.tenant_id:
            # For local mode or other cases without auth
            headers["x-caddi-tenant-id"] = self.tenant_id
        return headers

    def health_check(self) -> dict[str, Any]:
        """Check ISP API health status."""
        response = self.session.get(f"{self.base_url}/_health", timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        logger.info(f"ISP health: {result}")
        return result

    def index_exists(self, index_name: str) -> bool:
        """Check if an index exists."""
        try:
            response = self.session.get(
                f"{self.base_url}/aliases/{index_name}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                return isinstance(data, list) and len(data) > 0
            return False
        except Exception:
            return False

    def create_index(
        self,
        index_name: str,
        mappings: dict[str, Any],
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a search index."""
        logger.info(f"Creating index: {index_name}")

        body = {"mappings": mappings}
        if settings:
            body["settings"] = settings

        response = self.session.put(
            f"{self.base_url}/{index_name}",
            json=body,
            headers=self._headers(),
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            logger.error(f"Failed to create index: {response.status_code} - {response.text}")

        response.raise_for_status()
        return response.json()

    def delete_index(self, index_name: str) -> dict[str, Any]:
        """Delete a search index."""
        logger.info(f"Deleting index: {index_name}")
        response = self.session.delete(
            f"{self.base_url}/{index_name}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def setup_index(
        self,
        index_name: str,
        mappings: dict[str, Any],
        settings: dict[str, Any] | None = None,
        *,
        truncate: bool = False,
    ) -> dict[str, Any] | None:
        """Set up an index, optionally recreating it when truncate is true."""
        if self.index_exists(index_name):
            if not truncate:
                logger.info(f"Index exists, skipping create: {index_name}")
                return None
            self.delete_index(index_name)
        return self.create_index(index_name, mappings, settings)

    def index_document(
        self,
        index_name: str,
        doc_id: str,
        document: dict[str, Any],
        upsert: bool = False,
    ) -> dict[str, Any]:
        """Index a single document."""
        endpoint = "_doc" if upsert else "_create"
        response = self.session.put(
            f"{self.base_url}/{index_name}/{endpoint}/{doc_id}",
            json=document,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def delete_document(
        self,
        index_name: str,
        doc_id: str,
    ) -> dict[str, Any]:
        """Delete a single document."""
        response = self.session.delete(
            f"{self.base_url}/{index_name}/_doc/{doc_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def search(self, index_name: str, query: dict[str, Any]) -> dict[str, Any]:
        """Search documents in an index.

        spec: https://lexico.caddi.io/interactive-search-platform/api/1.5.2/release/#tag/search

        Args:
            index_name: ISP index alias.
            query: Full ISP search request body (e.g. {"query": {...}, "size": 10, "_source": False}).

        """
        response = self.session.post(
            f"{self.base_url}/{index_name}/_search",
            json=query,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def delete_by_query(
        self,
        index_name: str,
        query: dict[str, Any],
        batch_size: int = 1000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Delete documents matching a query by searching and deleting IDs.

        Note:
            ISP does not provide a native delete-by-query API, so this method loops
            over search results and deletes documents one by one.

        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        logger.info(
            "ISP delete_by_query start",
            index=index_name,
            batch_size=batch_size,
            dry_run=dry_run,
        )

        if dry_run:
            # Dry run uses a single request; size=10 limits payload while total hits is returned.
            body: dict[str, Any] = {
                "query": query,
                "_source": False,
                "size": 10,
            }
            response = self.search(index_name, body)
            total = response.get("hits", {}).get("total", 0)
            if isinstance(total, dict):
                total = total.get("value", 0)

            logger.info(
                "ISP delete_by_query in dry_run, max_size=10",
                index=index_name,
                total_found=total,
            )
            return {
                "total_found": total,
                "deleted": 0,
                "errors": 0,
                "error_details": None,
                "iterations": 1 if total else 0,
            }

        total_found = 0
        deleted = 0
        errors = 0
        error_details: list[str] = []
        iterations = 0

        while True:
            body: dict[str, Any] = {
                "query": query,
                "_source": False,
                "size": batch_size,
            }

            response = self.search(index_name, body)
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                # No more documents to delete and exit loop
                break

            iterations += 1

            for hit in hits:
                doc_id = hit.get("_id")
                if not doc_id:
                    errors += 1
                    error_details.append("Missing _id in search hit")
                    continue

                total_found += 1

                try:
                    self.delete_document(index_name, doc_id)
                    deleted += 1
                except Exception as e:
                    errors += 1
                    error_detail = str(e.__cause__) if e.__cause__ else str(e)
                    error_details.append(f"Failed to delete {doc_id}: {error_detail}")

        logger.info(
            "ISP delete_by_query complete",
            index=index_name,
            total_found=total_found,
            deleted=deleted,
            errors=errors,
            iterations=iterations,
        )
        return {
            "total_found": total_found,
            "deleted": deleted,
            "errors": errors,
            "error_details": error_details if error_details else None,
            "iterations": iterations,
        }

    def bulk_index_documents(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
        id_field: str = "id",
        upsert: bool = False,
    ) -> dict[str, Any]:
        """Bulk index multiple documents."""
        logger.info(f"Bulk indexing {len(documents)} documents into {index_name}")

        success_count = 0
        errors: list[str] = []

        for doc in documents:
            if id_field not in doc:
                errors.append(f"Document missing '{id_field}' field")
                continue

            try:
                self.index_document(index_name, str(doc[id_field]), doc, upsert=upsert)
                success_count += 1
            except Exception as e:
                # For RetryError, use the original cause
                error_detail = str(e.__cause__) if e.__cause__ else str(e)
                response = getattr(e, "response", None)
                if response is not None and response.text:
                    response_text = response.text.strip()
                    if len(response_text) > 1000:
                        response_text = f"{response_text[:1000]}...(truncated)"
                    error_detail = f"{error_detail} | response: {response_text}"
                errors.append(f"Failed to index {doc[id_field]}: {error_detail}")

        logger.info(f"Bulk indexing: {success_count}/{len(documents)} success, {len(errors)} errors")

        return {
            "total": len(documents),
            "success": success_count,
            "errors": len(errors),
            "error_details": errors if errors else None,
        }


def create_isp_client_from_env(local_mode: bool | None = None) -> ISPClient:
    """Create ISP client from environment variables.

    Authentication priority:
    1. If local_mode is true, skip authentication
    2. If M2M_INTERNAL_TOKEN is set, use it directly (for testing/debugging)
    3. If M2M_INTERNAL_TOKEN_CLIENT_ID and SECRET are set, obtain Internal Token from M2M Token Issuer
    """
    if local_mode is None:
        local_mode = os.getenv("LOCAL_MODE", "false").lower() == "true"

    if "ISP_API_URL" in os.environ:
        base_url = os.environ["ISP_API_URL"]
    elif local_mode:
        base_url = "http://localhost:3000"
    else:
        base_url = "http://isp-api.isp-agent-platform.svc.cluster.local:3000"

    tenant_id = os.getenv("TENANT_ID")
    if not tenant_id:
        raise ValueError("TENANT_ID environment variable is required")

    internal_token = None

    # Priority 1: Local mode skips authentication
    if local_mode:
        logger.info("Local mode enabled; skipping M2M Token Issuer")
    # Priority 2: Use M2M_INTERNAL_TOKEN directly if provided (for testing/debugging)
    elif os.getenv("M2M_INTERNAL_TOKEN"):
        internal_token = os.getenv("M2M_INTERNAL_TOKEN")
        logger.info("Using M2M_INTERNAL_TOKEN from environment")
    # Priority 3: Obtain from M2M Token Issuer if credentials are available
    elif os.getenv("M2M_INTERNAL_TOKEN_CLIENT_ID") and os.getenv("M2M_INTERNAL_TOKEN_CLIENT_SECRET"):
        logger.info("Obtaining Internal Token from M2M Token Issuer")
        m2m_client = create_m2m_token_issuer_client_from_env()
        internal_token = m2m_client.get_internal_token(tenant_id)

    logger.info(
        f"ISP client: url={base_url}, tenant={tenant_id}, "
        f"local={local_mode}, has_token={bool(internal_token)}"
    )

    return ISPClient(
        base_url=base_url,
        tenant_id=tenant_id,
        internal_token=internal_token,
    )
