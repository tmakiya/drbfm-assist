"""Elasticsearch manager with enhanced flexibility and functionality"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from elasticsearch import (
    AuthorizationException,
    ConflictError,
    ConnectionError,
    Elasticsearch,
    NotFoundError,
    RequestError,
    TransportError,
)
from elasticsearch.helpers import BulkIndexError, bulk
from loguru import logger

from drassist.utils import get_env


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


class ElasticsearchManager:
    """Elasticsearch client with enhanced index management and operations"""

    def __init__(
        self,
        config: Union[Dict[str, str], object],
        mapping_file: Optional[str] = None,
        logger_func: Optional[callable] = None,
    ):
        """Initialize Elasticsearch manager

        Args:
            config: Configuration object or dictionary with elasticsearch settings
            index_name: Index name (overrides config if provided)
            mapping_file: Path to mapping file (overrides default if provided)
            logger_func: Custom logger function

        """
        self.logger = logger_func or logger

        # Extract configuration
        self.es_url = get_env("ELASTICSEARCH_URL", "http://localhost:9200")
        self.index_name = config.elasticsearch["index"]

        # Set mapping file path
        if mapping_file:
            self.mapping_file = Path(mapping_file)
        elif hasattr(config, "elasticsearch") and "mapping_file" in config.elasticsearch:
            self.mapping_file = Path(config.elasticsearch["mapping_file"])
        else:
            tenant_id = getattr(config, "tenant_id", None)
            if not tenant_id:
                raise ValueError("tenant_id not found in config. Cannot determine mapping file.")
            self.mapping_file = Path(f"drassist/spec/elasticsearch/defects_{tenant_id}.json")

        self.logger.debug("Mapping file set to: {}", self.mapping_file)

        # Initialize Elasticsearch client
        self.client = Elasticsearch([self.es_url])

        # Test connection
        self._test_connection()

    def _test_connection(self) -> None:
        """Test Elasticsearch connection"""
        info = self.client.info()
        self.logger.info(f"Connected to Elasticsearch at {self.es_url}")
        self.logger.debug(f"Elasticsearch version: {info['version']['number']}")

    def load_mapping(self, mapping_file: Optional[str] = None) -> Dict[str, Any]:
        """Load Elasticsearch mapping from JSON file

        Args:
            mapping_file: Path to mapping file (uses default if not provided)

        Returns:
            Mapping configuration

        """
        file_path = Path(mapping_file) if mapping_file else self.mapping_file

        if not file_path.exists():
            raise FileNotFoundError(f"Mapping file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        self.logger.info(f"Loaded mapping from {file_path}")
        return mapping

    def index_exists(self, index_name: Optional[str] = None) -> bool:
        """Check if index exists"""
        index = index_name or self.index_name
        return self.client.indices.exists(index=index)

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
                self.client.indices.delete(index=index)
                message = f"Deleted existing index: {index}"
                self.logger.info(message)
                return IndexResult(success=True, message=message)
            else:
                message = f"Index does not exist: {index}"
                self.logger.info(message)
                return IndexResult(success=True, message=message)
        except (NotFoundError, AuthorizationException) as e:
            message = f"Failed to delete index {index}: {e}"
            self.logger.error(message)
            return IndexResult(success=False, message=message)
        except Exception as e:
            message = f"Unexpected error deleting index {index}: {e}"
            self.logger.error(message)
            return IndexResult(success=False, message=message)

    def create_index(
        self,
        index_name: Optional[str] = None,
        mapping: Optional[Dict[str, Any]] = None,
        mapping_file: Optional[str] = None,
        delete_existing: bool = True,
    ) -> IndexResult:
        """Create Elasticsearch index with mapping

        Args:
            index_name: Index name (uses default if not provided)
            mapping: Mapping configuration (loads from file if not provided)
            mapping_file: Path to mapping file
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

            # Load mapping if not provided
            if mapping is None:
                mapping = self.load_mapping(mapping_file)

            # Create index
            response = self.client.indices.create(
                index=index, settings=mapping["settings"], mappings=mapping["mappings"]
            )
            message = f"Created index: {index}"
            self.logger.info(message)

            return IndexResult(success=True, message=message, details=response)

        except (RequestError, ConflictError) as e:
            message = f"Failed to create index {index}: {e}"
            self.logger.error(message)
            return IndexResult(success=False, message=message)
        except Exception as e:
            message = f"Unexpected error creating index {index}: {e}"
            self.logger.error(message)
            return IndexResult(success=False, message=message)

    def index_documents(
        self,
        documents: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        chunk_size: int = 1000,
    ) -> BulkIndexResult:
        """Index documents to Elasticsearch using bulk API

        Args:
            documents: List of documents to index
            index_name: Index name (uses default if not provided)
            chunk_size: Size of bulk indexing chunks

        Returns:
            Result of bulk indexing operation

        """
        index = index_name or self.index_name

        try:
            # Prepare bulk actions
            actions = []
            for doc in documents:
                actions.append({"_index": index, "_source": doc})

            # Perform bulk indexing
            success_count = 0
            error_count = 0
            errors = []

            # Process in chunks
            for i in range(0, len(actions), chunk_size):
                chunk = actions[i : i + chunk_size]

                try:
                    bulk(self.client, chunk)
                    success_count += len(chunk)
                except (BulkIndexError, ConnectionError, TransportError) as e:
                    error_count += len(chunk)
                    errors.append(str(e))
                    self.logger.error(f"Bulk indexing chunk failed: {e}")
                    for err in e.errors:
                        self.logger.error(json.dumps(err, indent=2, ensure_ascii=False))
                except Exception as e:
                    error_count += len(chunk)
                    errors.append(str(e))
                    self.logger.error(f"Unexpected error in bulk indexing chunk: {e}")

            message = f"Indexed {success_count} documents to {index}"
            if error_count > 0:
                message += f" ({error_count} failed)"

            self.logger.info(message)

            return BulkIndexResult(
                success=error_count == 0,
                indexed_count=success_count,
                failed_count=error_count,
                errors=errors,
            )

        except (RequestError, ConnectionError, TransportError) as e:
            message = f"Failed to index documents: {e}"
            self.logger.error(message)
            return BulkIndexResult(
                success=False,
                indexed_count=0,
                failed_count=len(documents),
                errors=[str(e)],
            )
        except Exception as e:
            message = f"Unexpected error indexing documents: {e}"
            self.logger.error(message)
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
            query: Elasticsearch query
            index_name: Index to search (uses default if not provided)
            size: Number of results to return

        Returns:
            Search results

        """
        index = index_name or self.index_name

        try:
            response = self.client.search(index=index, body=query, size=size)
            return response
        except (NotFoundError, RequestError) as e:
            self.logger.error(f"Search failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected search error: {e}")
            raise

    def get_unique_categories(self, field_name: str, index_name: Optional[str] = None) -> List[str]:
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
                self.logger.warning(f"Index {index} does not exist")
                return []

            # Aggregation query to get unique values
            agg_query = {
                "size": 0,
                "aggs": {"unique_values": {"terms": {"field": field_name, "size": 1000}}},
            }

            response = self.client.search(index=index, body=agg_query)
            buckets = response["aggregations"]["unique_values"]["buckets"]

            values = [bucket["key"] for bucket in buckets]
            self.logger.info(f"Found {len(values)} unique values for field '{field_name}'")

            return values

        except (NotFoundError, RequestError) as e:
            self.logger.error(f"Failed to get unique values for field '{field_name}': {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error getting unique values for field '{field_name}': {e}")
            return []

    def get_index_info(self, index_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about the index"""
        index = index_name or self.index_name

        try:
            if not self.index_exists(index):
                return {"exists": False}

            stats = self.client.indices.stats(index=index)
            mapping = self.client.indices.get_mapping(index=index)

            return {
                "exists": True,
                "document_count": stats["indices"][index]["total"]["docs"]["count"],
                "size_bytes": stats["indices"][index]["total"]["store"]["size_in_bytes"],
                "mapping": mapping[index]["mappings"],
            }
        except (NotFoundError, AuthorizationException) as e:
            self.logger.error(f"Failed to get index info: {e}")
            return {"exists": False, "error": str(e)}
        except Exception as e:
            self.logger.error(f"Unexpected error getting index info: {e}")
            return {"exists": False, "error": str(e)}