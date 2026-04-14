"""Test script for querying ISP index.

This script demonstrates how to search documents in ISP index.

Query Examples:
1. Match all documents - retrieve all documents in the index
2. Search by specific original_id - using term query for exact match
3. Search by multiple original_ids - using terms query for multiple values
4. Count documents with embedding - check embedding statistics

Prerequisites:
- kubectl port-forward must be running:
  kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000
- TENANT_ID must be set in .env file
- Index must exist (run defects/main.py first to create and populate index)

Usage:
    cd ingestion
    uv run python tenants/dev/a7753ab8-12e3-44f0-9ae6-9e85637b890e/test/_isp_query.py
"""

import json
import os
import sys

from common.isp import create_isp_client_from_env
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger

INDEX_NAME = "defects"
EXAMPLE_2_ORIGINAL_ID = "35df5736-e46c-46d9-bd5f-c6167f38f95a"
EXAMPLE_3_ORIGINAL_IDS = [
    "35df5736-e46c-46d9-bd5f-c6167f38f95a",
    "dc865446-4115-4752-ad55-21185799c014",
]


def example_1_match_all(client, index_id):
    """Demonstrate matching all documents.

    Retrieves all documents in the index.
    """
    logger.info("=" * 80)
    logger.info("Example 1: Match All Documents")
    logger.info("=" * 80)

    query = {"query": {"match_all": {}}}
    results = client.search(index_id, query)
    logger.info(f"Total documents: {results['hits']['total']}")
    logger.info("")

    for i, hit in enumerate(results["hits"]["hits"], 1):
        logger.info(f"Document {i}:")
        logger.info(f"  original_id: {hit['_source'].get('original_id')}")
        logger.info(f"  doc_id: {hit['_source'].get('doc_id')}")
        logger.info(f"  cause.unit: {hit['_source'].get('cause', {}).get('unit')}")
        logger.info(f"  failure.mode: {hit['_source'].get('failure', {}).get('mode')}")
        logger.info("")

    return results


def example_2_search_by_original_id(client, index_id):
    """Demonstrate searching by specific original_id using term query.

    Args:
        client: ISP client instance
        index_id: Index name
        original_id: The original_id to search for

    """
    original_id = EXAMPLE_2_ORIGINAL_ID
    logger.info("=" * 80)
    logger.info("Example 2: Search by Specific original_id")
    logger.info("=" * 80)
    logger.info(f"Searching for original_id: {original_id}")

    # Use term query for exact match on keyword field
    # Note: ISP with matching: ["exact"] may not require .exact suffix
    # Include embedding in _source (it's excluded by default due to size)
    query = {
        "query": {"term": {"original_id": original_id}},
        "_source": ["*"],  # Explicitly request all fields including embedding
    }
    results = client.search(index_id, query)
    logger.info(f"Total documents with this original_id: {results['hits']['total']}")
    logger.info("")

    for i, hit in enumerate(results["hits"]["hits"], 1):
        logger.info(f"Document {i}:")
        source = hit["_source"].copy()

        # Truncate embedding to first 3 values for display
        if "embedding" in source and isinstance(source["embedding"], list):
            full_length = len(source["embedding"])
            source["embedding"] = source["embedding"][:3] + [f"... ({full_length} dimensions total)"]

        logger.info(json.dumps(source, indent=2, ensure_ascii=False))
        logger.info("")

    return results


def example_3_search_by_multiple_original_ids(client, index_id):
    """Demonstrate searching by multiple original_ids using terms query.

    Args:
        client: ISP client instance
        index_id: Index name

    """
    original_ids = EXAMPLE_3_ORIGINAL_IDS
    logger.info("=" * 80)
    logger.info("Example 3: Search by Multiple original_ids")
    logger.info("=" * 80)
    logger.info(f"Searching for {len(original_ids)} original_ids:")
    for oid in original_ids:
        logger.info(f"  - {oid}")
    logger.info("")

    # Use terms query for matching multiple values
    query = {
        "query": {"terms": {"original_id": original_ids}},
        "_source": ["*"],  # Explicitly request all fields including embedding
    }
    results = client.search(index_id, query)
    logger.info(f"Total documents matching these original_ids: {results['hits']['total']}")
    logger.info("")

    for i, hit in enumerate(results["hits"]["hits"], 1):
        logger.info(f"Document {i}:")
        source = hit["_source"].copy()

        # Truncate embedding to first 3 values for display
        if "embedding" in source and isinstance(source["embedding"], list):
            full_length = len(source["embedding"])
            source["embedding"] = source["embedding"][:3] + [f"... ({full_length} dimensions total)"]

        logger.info(json.dumps(source, indent=2, ensure_ascii=False))
        logger.info("")

    return results


def example_4_count_embeddings(client, index_id):
    """Demonstrate counting documents with embedding field.

    This demonstrates how to check how many documents have embeddings
    in the embedding field (root level).

    Args:
        client: ISP client instance
        index_id: Index name

    """
    logger.info("=" * 80)
    logger.info("Example 4: Count Documents with embedding")
    logger.info("=" * 80)

    # First, get total document count
    total_query = {"query": {"match_all": {}}, "size": 0}
    total_results = client.search(index_id, total_query)
    total_count = total_results["hits"]["total"]
    logger.info(f"Total documents in index: {total_count}")

    # Query to find documents where embedding exists
    embedding_query = {"query": {"exists": {"field": "embedding"}}, "size": 0}
    embedding_results = client.search(index_id, embedding_query)
    count_with_embedding = embedding_results["hits"]["total"]
    logger.info(f"Documents with embedding: {count_with_embedding}")

    # Calculate statistics
    count_without_embedding = total_count - count_with_embedding
    percentage = (count_with_embedding / total_count * 100) if total_count > 0 else 0

    logger.info(f"Documents without embedding: {count_without_embedding}")
    logger.info(f"Percentage with embedding: {percentage:.2f}%")
    logger.info("")

    # List documents without embedding
    if count_without_embedding > 0:
        logger.info(f"Documents without embedding ({count_without_embedding} total):")

        # Since ISP API doesn't support bool.must_not queries,
        # we need to fetch all documents and filter client-side
        all_docs_query = {
            "query": {"match_all": {}},
            "_source": ["*"],
            "size": min(1000, total_count),  # Fetch up to 1000 docs
        }
        all_docs_results = client.search(index_id, all_docs_query)

        # Filter documents without embedding
        docs_without_embedding = []
        for hit in all_docs_results["hits"]["hits"]:
            source = hit["_source"]
            # Check if embedding field is missing or None
            if "embedding" not in source or source.get("embedding") is None:
                docs_without_embedding.append(source)

        # Collect all original_ids
        original_ids = [source.get("original_id") for source in docs_without_embedding]

        logger.info(f"  original_id list ({len(original_ids)} found):")
        logger.info("\n" + "\n".join(f"{id}" for id in original_ids))
        logger.info("")

    # Show a few sample documents with embeddings
    if count_with_embedding > 0:
        logger.info("Sample documents with embedding:")
        sample_query = {
            "query": {"exists": {"field": "embedding"}},
            "_source": ["original_id", "doc_id", "embedding"],
            "size": 3,
        }
        sample_results = client.search(index_id, sample_query)

        for i, hit in enumerate(sample_results["hits"]["hits"], 1):
            source = hit["_source"]
            logger.info(f"  Sample {i}:")
            logger.info(f"    original_id: {source.get('original_id')}")
            logger.info(f"    doc_id: {source.get('doc_id')}")

            # Show embedding info if present
            embedding = source.get("embedding")
            if embedding and isinstance(embedding, list):
                embedding_length = len(embedding)
                embedding_preview = embedding[:3]
                logger.info(
                    f"    embedding: [{', '.join(map(str, embedding_preview))}, ... "
                    f"({embedding_length} dimensions total)]"
                )
            logger.info("")

    logger.info("=" * 80)
    logger.info("")

    return {
        "total_count": total_count,
        "count_with_embedding": count_with_embedding,
        "count_without_embedding": count_without_embedding,
        "percentage": percentage,
    }


def main():
    """Query ISP index and display results."""
    # Configure logger to show only INFO and above (hide DEBUG)
    logger.remove()  # Remove default handler
    logger.add(sys.stderr, level="INFO")  # Add handler with INFO level

    # Load environment variables from .env file
    ingestion_root = get_ingestion_root()
    env_path = ingestion_root / ".env"
    if not env_path.exists():
        logger.error(f".env not found at {env_path}")
        logger.error("Please ensure ingestion/.env file exists with required settings")
        sys.exit(1)

    load_dotenv(env_path)

    logger.info("=" * 80)
    logger.info("ISP Index Query Test Script")
    logger.info("=" * 80)
    logger.info("")

    # Get tenant ID from environment
    tenant_id = os.getenv("TENANT_ID")
    if not tenant_id:
        logger.error("TENANT_ID environment variable is required")
        sys.exit(1)

    # Initialize ISP client in local mode
    try:
        client = create_isp_client_from_env(local_mode=True)
        logger.info("✓ ISP Client initialized (local mode)")
    except Exception as e:
        logger.error(f"Failed to initialize ISP client: {e}")
        logger.error("Make sure kubectl port-forward is running:")
        logger.error("  kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000")
        sys.exit(1)

    # Index name
    # Format: drbfm-assist-[INDEX_NAME]_{tenant_id}
    index_id = f"drbfm-assist-{INDEX_NAME}_{tenant_id}"
    logger.info(f"Index name: {index_id}")
    logger.info("")

    try:
        # Note: Skipping index_exists() check as it may not work reliably
        # Will attempt to query directly and handle errors if index doesn't exist
        logger.info(f"Attempting to query index: {index_id}")
        logger.info("")

        # Examples
        example_1_match_all(client, index_id)
        example_2_search_by_original_id(client, index_id)
        example_3_search_by_multiple_original_ids(client, index_id)
        example_4_count_embeddings(client, index_id)

    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
