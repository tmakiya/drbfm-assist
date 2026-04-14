"""Cleanup test ISP index.

This script deletes test indices created during testing.
"""

import os
import sys

from common.isp import create_isp_client_from_env
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger


def main():
    """Delete test ISP index."""
    ingestion_root = get_ingestion_root()
    load_dotenv(ingestion_root / ".env")

    tenant_id = os.getenv("TENANT_ID")
    # ISP requires format: {name}_{tenant_id}
    # Format: drbfm-assist-[index_name]_{tenant_id}
    test_index_name = f"drbfm-assist-test_{tenant_id}"

    logger.info("ISP Test Index Cleanup")
    logger.info("=" * 80)

    isp_client = create_isp_client_from_env()

    # Check if index exists
    if not isp_client.index_exists(test_index_name):
        logger.info(f"✓ Test index '{test_index_name}' does not exist. Nothing to clean up.")
        return

    # Delete the index
    logger.info(f"Deleting test index: {test_index_name}")
    try:
        result = isp_client.delete_index(test_index_name)
        logger.info(f"✓ Test index deleted successfully: {result}")
    except Exception as e:
        logger.error(f"Failed to delete test index: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
