"""Query script for MSQP via SOCKS5 proxy (local execution)."""

import sys

from common.msqp import create_msqp_client_from_env
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger


def main():
    """Execute SELECT query on MSQP via SOCKS5 proxy."""
    # Load environment variables from .env file (in ingestion/ directory)
    ingestion_root = get_ingestion_root()
    env_path = ingestion_root / ".env"
    if not env_path.exists():
        logger.error(f".env not found at {env_path}")
        logger.error("Please ensure ingestion/.env file exists with required credentials")
        sys.exit(1)

    load_dotenv(env_path)

    logger.info("=" * 60)
    logger.info("MSQP Query via SOCKS5 Proxy (Local mode)")
    logger.info("=" * 60)
    logger.info("NOTE: Make sure SOCKS5 proxy is running!")
    logger.info("  Run: source setup_local_proxy.sh")
    logger.info("")

    # Create MSQP client in local mode (SOCKS5 proxy)
    try:
        client = create_msqp_client_from_env(local_mode=True)
    except Exception as e:
        logger.error(f"Failed to create MSQP client: {e}")
        logger.error("")
        logger.error("Possible issues:")
        logger.error("  1. SOCKS5 proxy is not running")
        logger.error("  2. Bastion server is not accessible")
        logger.error("  3. Authentication credentials are incorrect")
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("  1. Check if setup_socks_proxy.sh is running")
        logger.error(
            "  2. Test proxy: curl --proxy socks5://localhost:1080 https://msqp-auth.dp.internal.caddi.io"
        )
        sys.exit(1)

    # Execute SELECT query
    logger.info("Executing queries...")
    logger.info("")

    try:
        logger.info("=== Available Tables ===")
        tables = client.list_tables()
        logger.info(f"Found {len(tables)} tables in {client.catalog}.{client.schema}:")
        for table in tables:
            logger.info(f"  - {table}")
        logger.info("")

        # If drawing_page table exists, query it
        if "drawing_page" in tables:
            logger.info("=== Query: SELECT * FROM drawing_page ===")
            df = client.query("SELECT * FROM drawing_page limit 10")
            logger.info(f"Query returned {len(df)} rows")
            logger.info(f"\n{df.to_string()}")
        else:
            logger.warning("Table 'drawing' not found")
            logger.info("")
            logger.info("=== Query: SHOW SCHEMAS ===")
            df = client.query(f"SHOW SCHEMAS FROM {client.catalog}")
            logger.info(f"\n{df.to_string()}")

        logger.info("")
        logger.info("=" * 60)
        logger.info("Query completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
