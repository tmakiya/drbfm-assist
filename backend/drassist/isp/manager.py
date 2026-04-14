"""ISP manager with enhanced flexibility and functionality"""

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

import structlog

logger = structlog.stdlib.get_logger(__name__)
from requests import HTTPError

from .client import ISPClient


@dataclass
class IndexResult:
    """Result of index operations"""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class BulkIndexResult:
    """Result of bulk indexing operations"""

    success: bool
    indexed_count: int
    failed_count: int
    errors: List[str]


class ISPManager:
    """ISP client with enhanced index management and operations

    Environment variables:
        ISP_URL: ISP server URL (default: http://localhost:50080)
        ISP_AUTH_TOKEN: Authentication token for ISP API
        ISP_INDEX: Default index name (overrides config file)
    """

    def __init__(
        self,
        config: Union[Dict[str, str], object],
        logger_func: Optional[Callable[..., Any]] = None,
        auth_token: Optional[str] = None,
    ):
        """Initialize ISP manager

        Args:
            config: Configuration object or dictionary with isp settings
            logger_func: Custom logger function
            auth_token: Optional authentication token for ISP API.
                       If provided, takes precedence over ISP_AUTH_TOKEN env var.

        Environment variables take precedence over config file settings.

        """
        self.logger = logger_func or logger

        # Extract configuration
        if hasattr(config, "isp"):
            isp_config = config.isp
        elif isinstance(config, dict):
            isp_config = config.get("isp", {})
        else:
            isp_config = {}

        # Environment variable takes precedence over config file
        self.index_name = os.environ.get("ISP_INDEX") or isp_config.get("index", "")

        # Initialize ISP client with optional auth token
        self.client = ISPClient(auth_token=auth_token)

    def set_internal_token(self, internal_token: str) -> None:
        """Set or update the internal token for authentication.

        Args:
            internal_token: The internal token to use for ISP API requests
        """
        self.client.set_internal_token(internal_token)

    def index_exists(self, index_name: Optional[str] = None) -> bool:
        """Check if index exists"""
        index = index_name or self.index_name
        try:
            self.client.get_mappings(index)
            return True
        except HTTPError as e:
            if e.response.status_code == 404:
                return False
            raise

    def delete_index(self, index_name: Optional[str] = None) -> IndexResult:
        """Delete index if it exists

        Args:
            index_name: Index to delete (uses default if not provided)

        Returns:
            Result of delete operation

        """
        index = index_name or self.index_name

        try:
            if self.index_exists(index):
                self.client.delete_index(index)
                self.logger.info("Deleted existing index", index=index)
                return IndexResult(success=True, message=f"Deleted existing index: {index}")
            else:
                self.logger.info("Index does not exist", index=index)
                return IndexResult(success=True, message=f"Index does not exist: {index}")
        except HTTPError as e:
            self.logger.error("Failed to delete index", index=index, error=str(e))
            return IndexResult(success=False, message=f"Failed to delete index {index}: {e}")
        except Exception as e:
            self.logger.error("Unexpected error deleting index", index=index, error=str(e))
            return IndexResult(success=False, message=f"Unexpected error deleting index {index}: {e}")

    def create_index(
        self,
        index_name: Optional[str] = None,
        mapping: Optional[Dict[str, Any]] = None,
        delete_existing: bool = True,
    ) -> IndexResult:
        """Create ISP index with mapping

        Args:
            index_name: Index name (uses default if not provided)
            mapping: Mapping configuration
            delete_existing: Whether to delete existing index

        Returns:
            Result of create operation

        """
        index = index_name or self.index_name

        try:
            # Delete existing index if requested
            if delete_existing and self.index_exists(index):
                delete_result = self.delete_index(index)
                if not delete_result.success:
                    return delete_result

            # Create index with mappings
            if mapping is None:
                mapping = {"dynamic": "strict", "properties": {}}

            response = self.client.create_index(index, mapping)
            self.logger.info("Created index", index=index)

            return IndexResult(success=True, message=f"Created index: {index}", details=response)

        except HTTPError as e:
            self.logger.error("Failed to create index", index=index, error=str(e))
            return IndexResult(success=False, message=f"Failed to create index {index}: {e}")
        except Exception as e:
            self.logger.error("Unexpected error creating index", index=index, error=str(e))
            return IndexResult(success=False, message=f"Unexpected error creating index {index}: {e}")

    def index_documents(
        self,
        documents: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        chunk_size: int = 1000,
        id_field: str = "doc_id",
    ) -> BulkIndexResult:
        """Index documents to ISP using bulk API

        Args:
            documents: List of documents to index
            index_name: Index name (uses default if not provided)
            chunk_size: Size of bulk indexing chunks
            id_field: Field to use as document ID

        Returns:
            Result of bulk indexing operation

        """
        index = index_name or self.index_name

        try:
            success_count = 0
            error_count = 0
            errors = []

            # Process in chunks
            for i in range(0, len(documents), chunk_size):
                chunk = documents[i : i + chunk_size]

                # Convert to ISP bulk format
                bulk_docs: List[Dict[str, Any]] = []
                for doc in chunk:
                    doc_id = doc.get(id_field, str(i + len(bulk_docs)))
                    bulk_docs.append({"_id": doc_id, "document": doc})

                try:
                    result = self.client.bulk_index(index, bulk_docs)
                    successful = result.get("successful", len(chunk))
                    failed = result.get("failed", 0)
                    success_count += successful
                    error_count += failed
                    if result.get("errors"):
                        errors.extend(result.get("errors", []))
                except HTTPError as e:
                    error_count += len(chunk)
                    errors.append(str(e))
                    self.logger.error("Bulk indexing chunk failed", error=str(e))
                except Exception as e:
                    error_count += len(chunk)
                    errors.append(str(e))
                    self.logger.error("Unexpected error in bulk indexing chunk", error=str(e))

            self.logger.info(
                "Indexed documents",
                index=index,
                success_count=success_count,
                error_count=error_count,
            )

            return BulkIndexResult(
                success=error_count == 0,
                indexed_count=success_count,
                failed_count=error_count,
                errors=errors,
            )

        except Exception as e:
            self.logger.error("Unexpected error indexing documents", error=str(e))
            return BulkIndexResult(
                success=False,
                indexed_count=0,
                failed_count=len(documents),
                errors=[str(e)],
            )

    def search(
        self, query: Dict[str, Any], index_name: Optional[str] = None, size: int = 10
    ) -> Dict[str, Any]:
        """Perform search query

        Args:
            query: Search query (can be in Elasticsearch format or ISP format)
            index_name: Index to search (uses default if not provided)
            size: Number of results to return

        Returns:
            Search results in Elasticsearch-compatible format

        """
        index = index_name or self.index_name

        try:
            # Check if query has "query" key (Elasticsearch format) or is direct query
            if "query" in query:
                search_query = query["query"]
            else:
                search_query = query

            self.logger.debug("Search", index=index, query=search_query)

            # Check for knn query
            if "knn" in query:
                knn_config = query["knn"]
                filter_query = knn_config.get("filter")
                try:
                    response = self.client.knn_search(
                        alias=index,
                        field=knn_config.get("field", "embedding"),
                        query_vector=knn_config["query_vector"],
                        k=knn_config.get("k", size),
                        num_candidates=knn_config.get("num_candidates", max(size * 10, 100)),
                        filter_query=filter_query,
                    )
                except HTTPError as e:
                    # KNN search may fail if embedding field doesn't exist
                    # Return empty results instead of raising
                    if e.response.status_code == 404:
                        self.logger.warning(
                            "KNN search not available, returning empty results", index=index
                        )
                        return {"hits": {"total": 0, "hits": []}}
                    raise
            else:
                response = self.client.search(index, search_query, size=size)

            return response
        except HTTPError as e:
            self.logger.error("Search failed", error=str(e))
            raise
        except Exception as e:
            self.logger.error("Unexpected search error", error=str(e))
            raise

    def get_unique_categories(
        self, field_name: str, index_name: Optional[str] = None
    ) -> List[str]:
        """Get unique values from a specified field using aggregation

        Args:
            field_name: The field to get unique values from
            index_name: Index name (uses default if not provided)

        Returns:
            List of unique field values

        """
        index = index_name or self.index_name

        try:
            if not self.index_exists(index):
                self.logger.warning("Index does not exist", index=index)
                return []

            # Use match_all query with aggregation
            response = self.client.search(
                index,
                {"match_all": {}},
                size=0,
                aggs={"unique_values": {"terms": {"field": field_name, "size": 1000}}},
            )
            buckets = response.get("aggregations", {}).get("unique_values", {}).get("buckets", [])

            values = [bucket["key"] for bucket in buckets]
            self.logger.info("Found unique values", field=field_name, count=len(values))

            return values

        except HTTPError as e:
            self.logger.error("Failed to get unique values", field=field_name, error=str(e))
            return []
        except Exception as e:
            self.logger.error(
                "Unexpected error getting unique values", field=field_name, error=str(e)
            )
            return []

    def get_index_info(self, index_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about the index"""
        index = index_name or self.index_name

        try:
            if not self.index_exists(index):
                return {"exists": False}

            mapping = self.client.get_mappings(index)

            return {
                "exists": True,
                "mapping": mapping,
            }
        except HTTPError as e:
            self.logger.error("Failed to get index info", error=str(e))
            return {"exists": False, "error": str(e)}
        except Exception as e:
            self.logger.error("Unexpected error getting index info", error=str(e))
            return {"exists": False, "error": str(e)}
