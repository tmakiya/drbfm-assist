"""Test script for ISP client with M2M Token Issuer authentication.

This script demonstrates how to create an ISP client that automatically
obtains an Internal Token from M2M Token Issuer.

Prerequisites:
- M2M_INTERNAL_TOKEN_CLIENT_ID must be set in .env file
- M2M_INTERNAL_TOKEN_CLIENT_SECRET must be set in .env file
- TENANT_ID must be set in .env file
- (Optional) ISP_API_URL for local development

For local development:
- kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000
- Set ISP_API_URL=http://localhost:3000 in .env

Usage:
    # Run from project root:
    uv run python ingestion/tenants/dev/a7753ab8-12e3-44f0-9ae6-9e85637b890e/sample/_test_isp_with_m2m.py
"""

import os
import sys

from common.isp import create_isp_client_from_env
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger


def main():
    """Test ISP client with M2M Token Issuer authentication."""
    # Load environment variables from .env
    ingestion_root = get_ingestion_root()
    env_path = ingestion_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment from {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}")

    # Get required environment variables
    tenant_id = os.getenv("TENANT_ID")
    if not tenant_id:
        logger.error("TENANT_ID environment variable is required")
        sys.exit(1)

    logger.info(f"Testing ISP client with M2M Token Issuer for tenant: {tenant_id}")

    try:
        # Create ISP client (automatically obtains Internal Token if needed)
        logger.info("Creating ISP client...")
        isp_client = create_isp_client_from_env()

        # Test health check
        logger.info("Testing ISP health check...")
        health = isp_client.health_check()
        logger.success(f"ISP health check passed: {health}")

        # Test index existence check (example)
        test_index = "test_index"
        logger.info(f"Checking if index '{test_index}' exists...")
        exists = isp_client.index_exists(test_index)
        logger.info(f"Index '{test_index}' exists: {exists}")

        logger.success("ISP client test completed successfully!")

    except Exception as e:
        logger.error(f"ISP client test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
