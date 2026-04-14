"""ISP Client utility for Python.

This module provides a simple wrapper for Interactive Search Platform API calls.
"""

import os
from typing import Any, Dict, List, Optional

import requests
import structlog

logger = structlog.get_logger()


class ISPClient:
    """Simple ISP API client using requests."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
    ):
        """Initialize ISP client.

        Args:
            base_url: ISP server URL (e.g., "http://localhost:50080")
                     If not provided, uses ISP_URL environment variable
            auth_token: Optional internal auth token for multi-tenant setups
                       If not provided, uses ISP_AUTH_TOKEN environment variable
        """
        url = base_url or os.environ.get("ISP_URL") or "http://localhost:50080"
        self.base_url = url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        token = auth_token or os.environ.get("ISP_AUTH_TOKEN")
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def set_internal_token(self, internal_token: str) -> None:
        """Set or update the internal token for authentication.

        Args:
            internal_token: The internal token to use for API requests
        """
        self.headers["Authorization"] = f"Bearer {internal_token}"

    def health(self) -> Dict[str, Any]:
        """Check ISP health status."""
        response = requests.get(f"{self.base_url}/_health", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_index(self, alias: str, mappings: Dict[str, Any]) -> Dict[str, Any]:
        """Create index with mappings.

        Args:
            alias: Index alias name (format: {type}_{tenant_id})
            mappings: Mapping definition

        Returns:
            Response with alias name
        """
        response = requests.put(
            f"{self.base_url}/{alias}",
            json={"mappings": mappings},
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def delete_index(self, alias: str) -> Dict[str, Any]:
        """Delete index and alias."""
        response = requests.delete(f"{self.base_url}/{alias}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_mappings(self, alias: str) -> Dict[str, Any]:
        """Get current mappings for alias."""
        response = requests.get(f"{self.base_url}/{alias}/_mappings", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def update_mappings(self, alias: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Update mappings (add new fields only).

        Args:
            alias: Index alias name
            properties: New field definitions to add
        """
        response = requests.put(
            f"{self.base_url}/{alias}/_mappings",
            json={"properties": properties},
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def index_document(
        self, alias: str, doc_id: str, document: Dict[str, Any], create: bool = False
    ) -> Dict[str, Any]:
        """Index a document.

        Args:
            alias: Index alias name
            doc_id: Document ID
            document: Document data
            create: If True, fail if document exists (use _create endpoint)
        """
        endpoint = "_create" if create else "_doc"
        response = requests.put(
            f"{self.base_url}/{alias}/{endpoint}/{doc_id}",
            json=document,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def bulk_index(self, alias: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Bulk index documents.

        Args:
            alias: Index alias name
            documents: List of {"_id": "...", "document": {...}} objects
        """
        response = requests.post(
            f"{self.base_url}/{alias}/_bulk", json=documents, headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_document(self, alias: str, doc_id: str) -> Dict[str, Any]:
        """Get document by ID."""
        response = requests.get(f"{self.base_url}/{alias}/_doc/{doc_id}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def delete_document(self, alias: str, doc_id: str) -> Dict[str, Any]:
        """Delete document by ID."""
        response = requests.delete(f"{self.base_url}/{alias}/_doc/{doc_id}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def search(self, alias: str, query: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Search documents.

        Args:
            alias: Index alias name
            query: Elasticsearch-style query DSL
            **kwargs: Additional search parameters (size, from_, sort, _source, aggs)
        """
        body = {"query": query}
        body.update(kwargs)

        response = requests.post(
            f"{self.base_url}/{alias}/_search", json=body, headers=self.headers
        )
        if not response.ok:
            logger.error(
                "ISP search error",
                status_code=response.status_code,
                response_text=response.text,
                request_body=body,
            )
        response.raise_for_status()
        return response.json()

    def knn_search(
        self,
        alias: str,
        field: str,
        query_vector: List[float],
        k: int = 10,
        num_candidates: int = 100,
        filter_query: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """k-NN vector search.

        Args:
            alias: Index alias name
            field: Vector field name
            query_vector: Query vector
            k: Number of nearest neighbors
            num_candidates: Number of candidates to consider
            filter_query: Optional filter query
        """
        body = {
            "knn": {
                "field": field,
                "query_vector": query_vector,
                "k": k,
                "num_candidates": num_candidates,
            }
        }
        if filter_query:
            body["filter"] = filter_query

        response = requests.post(
            f"{self.base_url}/{alias}/_knn_search", json=body, headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def reindex(
        self,
        alias: str,
        mappings: Optional[Dict[str, Any]] = None,
        wait_for_completion: bool = False,
    ) -> Dict[str, Any]:
        """Start reindex operation.

        Args:
            alias: Index alias name
            mappings: New mappings (if None, reuse existing)
            wait_for_completion: Wait for completion

        Returns:
            Response with task_id
        """
        body: Dict[str, Any] = {"wait_for_completion": wait_for_completion}
        if mappings:
            body["mappings"] = mappings

        response = requests.post(
            f"{self.base_url}/{alias}/_reindex", json=body, headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def start_refeed(self, alias: str, mappings: Dict[str, Any]) -> Dict[str, Any]:
        """Start refeed operation.

        Returns:
            Response with task_id
        """
        response = requests.post(
            f"{self.base_url}/{alias}/_refeed",
            json={"mappings": mappings},
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def refeed_bulk(
        self, alias: str, task_id: str, documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk index documents during refeed.

        Args:
            alias: Index alias name
            task_id: Refeed task ID
            documents: List of {"_id": "...", "document": {...}} objects
        """
        response = requests.post(
            f"{self.base_url}/{alias}/_refeed/{task_id}/_bulk",
            json=documents,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def complete_refeed(self, alias: str, task_id: str) -> Dict[str, Any]:
        """Complete refeed operation."""
        response = requests.post(
            f"{self.base_url}/{alias}/_refeed/{task_id}/_complete", headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get task status."""
        response = requests.get(f"{self.base_url}/_tasks/{task_id}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """Cancel running task."""
        response = requests.post(
            f"{self.base_url}/_tasks/{task_id}/_cancel", headers=self.headers
        )
        response.raise_for_status()
        return response.json()
