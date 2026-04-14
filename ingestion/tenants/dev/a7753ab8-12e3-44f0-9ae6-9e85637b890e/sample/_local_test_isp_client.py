"""Test script for ISP Client (Local development mode).

This script demonstrates how to:
1. Connect to ISP API via kubectl port-forward (localhost:3000)
2. Create a search index
3. Index documents
4. Search for documents
5. Clean up test data

Prerequisites:
- kubectl port-forward must be running:
  kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000
- TENANT_ID must be set in .env file

Note: This script uses local_mode=True to connect via localhost:3000
"""

import os
import sys

from common.isp import create_isp_client_from_env
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger


def main():
    """Test ISP Client functionality."""
    # Load environment variables from .env file
    ingestion_root = get_ingestion_root()
    env_path = ingestion_root / ".env"
    if not env_path.exists():
        logger.error(f".env not found at {env_path}")
        logger.error("Please ensure ingestion/.env file exists with required settings")
        logger.error("For local development, set ISP_API_URL=http://localhost:3000")
        sys.exit(1)

    load_dotenv(env_path)

    logger.info("=" * 80)
    logger.info("ISP Client Test Script (Local Mode)")
    logger.info("=" * 80)
    logger.info("NOTE: This script uses local_mode=True")
    logger.info("  ISP API URL: http://localhost:3000 (via kubectl port-forward)")
    logger.info(f"  TENANT_ID: {os.getenv('TENANT_ID', 'not set')}")
    logger.info("")

    # Initialize ISP client in local mode (kubectl port-forward to localhost:3000)
    try:
        client = create_isp_client_from_env(local_mode=True)
        logger.info("✓ ISP Client initialized (local mode)")
    except Exception as e:
        logger.error(f"Failed to initialize ISP client: {e}")
        logger.error("Make sure kubectl port-forward is running:")
        logger.error("  kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000")
        sys.exit(1)

    # Get tenant ID from environment
    tenant_id = os.getenv("TENANT_ID")
    if not tenant_id:
        logger.error("TENANT_ID environment variable is required")
        sys.exit(1)

    # Generate unique index name for testing
    # ISP requires format: {name}_{tenant_id}
    # Format: drbfm-assist-[index_name]_{tenant_id}
    test_index = f"drbfm-assist-test_{tenant_id}"
    logger.info(f"Test index name: {test_index}")
    logger.info("")

    try:
        # Test 1: Health Check
        logger.info("=" * 80)
        logger.info("Test 1: Health Check")
        logger.info("=" * 80)
        health = client.health_check()
        logger.info(f"Health status: {health}")
        logger.info("")

        # Test 2: Create Index
        logger.info("=" * 80)
        logger.info("Test 2: Create Index")
        logger.info("=" * 80)
        mappings = {
            "properties": {
                "id": {"type": "string", "matching": ["exact"]},
                "title": {"type": "string", "matching": ["japanese"]},
                "content": {"type": "string", "matching": ["japanese"]},
                "created_at": {"type": "string", "matching": ["exact"]},
            }
        }
        result = client.create_index(test_index, mappings)
        logger.info(f"Index created: {result}")
        logger.info("")

        # Test 3: Index Documents
        logger.info("=" * 80)
        logger.info("Test 3: Index Documents")
        logger.info("=" * 80)

        # Sample documents
        documents = [
            {
                "id": "1",
                "title": "テスト文書1",
                "content": "これは最初のテストドキュメントです。検索機能をテストします。",
                "created_at": "2025-12-09T00:00:00Z",
            },
            {
                "id": "2",
                "title": "テスト文書2",
                "content": "二番目のドキュメントです。日本語の全文検索をテストします。",
                "created_at": "2025-12-09T01:00:00Z",
            },
            {
                "id": "3",
                "title": "サンプルデータ",
                "content": "このドキュメントにはサンプルという単語が含まれています。",
                "created_at": "2025-12-09T02:00:00Z",
            },
        ]

        for doc in documents:
            result = client.index_document(test_index, doc["id"], doc)
            logger.info(f"Indexed document {doc['id']}: {result}")

        logger.info("")

        # Test 4: Search for Documents
        logger.info("=" * 80)
        logger.info("Test 4: Search for Documents")
        logger.info("=" * 80)

        # Search query 1: Match phrase
        logger.info("Search Query 1: Match phrase 'テスト'")
        query1 = {"query": {"match_phrase": {"content.japanese": "テスト"}}}
        results1 = client.search(test_index, query1)
        logger.info(f"Found {results1['hits']['total']} documents")
        for hit in results1["hits"]["hits"]:
            logger.info(f"  - [{hit['_id']}] {hit['_source']['title']}")
        logger.info("")

        # Search query 2: Match phrase for different term
        logger.info("Search Query 2: Match phrase 'サンプル'")
        query2 = {"query": {"match_phrase": {"content.japanese": "サンプル"}}}
        results2 = client.search(test_index, query2)
        logger.info(f"Found {results2['hits']['total']} documents")
        for hit in results2["hits"]["hits"]:
            logger.info(f"  - [{hit['_id']}] {hit['_source']['title']}")
        logger.info("")

        # Search query 3: Search in title field
        logger.info("Search Query 3: Match phrase in title '文書'")
        query3 = {"query": {"match_phrase": {"title.japanese": "文書"}}}
        results3 = client.search(test_index, query3)
        logger.info(f"Found {results3['hits']['total']} documents")
        for hit in results3["hits"]["hits"]:
            logger.info(f"  - [{hit['_id']}] {hit['_source']['title']}")
        logger.info("")

        # Test 5: Bulk Index Documents
        logger.info("=" * 80)
        logger.info("Test 5: Bulk Index Documents")
        logger.info("=" * 80)

        bulk_docs = [
            {
                "id": "4",
                "title": "バルクインデックステスト1",
                "content": "バルクインデックス機能のテストです。",
                "created_at": "2025-12-09T03:00:00Z",
            },
            {
                "id": "5",
                "title": "バルクインデックステスト2",
                "content": "複数のドキュメントを一度に登録できます。",
                "created_at": "2025-12-09T04:00:00Z",
            },
        ]

        bulk_result = client.bulk_index_documents(test_index, bulk_docs)
        logger.info(f"Bulk indexing result: {bulk_result}")
        logger.info("")

        # Final search to verify all documents
        logger.info("=" * 80)
        logger.info("Final Verification: Count All Documents")
        logger.info("=" * 80)
        all_query = {"query": {"match_all": {}}}
        all_results = client.search(test_index, all_query)
        logger.info(f"Total documents in index: {all_results['hits']['total']}")
        logger.info("")

        logger.info("=" * 80)
        logger.info("✓ All tests completed successfully!")
        logger.info("=" * 80)
        logger.info("")

        # Cleanup: Delete test index
        logger.info("=" * 80)
        logger.info("Cleanup: Deleting Test Index")
        logger.info("=" * 80)
        try:
            result = client.delete_index(test_index)
            logger.info(f"✓ Test index deleted: {result}")
        except Exception as e:
            logger.warning(f"Failed to delete test index: {e}")
            logger.warning(f"You may need to delete '{test_index}' manually")
        logger.info("")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        logger.info("")
        logger.warning(f"Test index '{test_index}' may still exist.")
        logger.warning("You may need to delete it manually if it was created.")
        sys.exit(1)


if __name__ == "__main__":
    main()
