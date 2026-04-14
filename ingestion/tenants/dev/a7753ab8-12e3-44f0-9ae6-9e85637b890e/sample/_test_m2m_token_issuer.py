"""Test script for M2M Token Issuer client.

This script demonstrates how to obtain an Internal Token from M2M Token Issuer.

Prerequisites:
- M2M_INTERNAL_TOKEN_CLIENT_ID must be set in .env file
- M2M_INTERNAL_TOKEN_CLIENT_SECRET must be set in .env file
- TENANT_ID must be set in .env file

Usage:
    # Run from project root:
    uv run python ingestion/tenants/dev/a7753ab8-12e3-44f0-9ae6-9e85637b890e/sample/_test_m2m_token_issuer.py
"""

import os
import sys

from common.m2m_token_issuer import create_m2m_token_issuer_client_from_env
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger


def main():
    """Test M2M Token Issuer client."""
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

    client_id = os.getenv("M2M_INTERNAL_TOKEN_CLIENT_ID")
    client_secret = os.getenv("M2M_INTERNAL_TOKEN_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.error("M2M_INTERNAL_TOKEN_CLIENT_ID and M2M_INTERNAL_TOKEN_CLIENT_SECRET are required")
        logger.info("Please set these environment variables in .env file")
        sys.exit(1)

    logger.info(f"Testing M2M Token Issuer client for tenant: {tenant_id}")

    try:
        # Create client
        client = create_m2m_token_issuer_client_from_env()

        # Obtain Internal Token
        logger.info("Requesting Internal Token...")
        internal_token = client.get_internal_token(tenant_id)

        # Display result
        logger.success("Successfully obtained Internal Token!")
        logger.info(f"Token (first 50 chars): {internal_token[:50]}...")
        logger.info(f"Token length: {len(internal_token)} characters")

        # Decode JWT header and payload (without verification)
        import base64
        import json

        try:
            # Split JWT into parts
            parts = internal_token.split(".")
            if len(parts) == 3:
                header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))

                logger.info("Token Header:")
                logger.info(f"  {json.dumps(header, indent=2)}")
                logger.info("Token Payload:")
                logger.info(f"  {json.dumps(payload, indent=2)}")
        except Exception as e:
            logger.warning(f"Failed to decode JWT: {e}")

    except Exception as e:
        logger.error(f"Failed to obtain Internal Token: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
