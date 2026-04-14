"""Sample query script for MSQP.

This script demonstrates how to:
1. Connect to MSQP (mode auto-detected from LOCAL_MODE environment variable)
2. List available tables
3. Switch catalogs and schemas using USE statement
4. Execute queries against different tables
5. Retrieve table schema information

Modes:
- LOCAL_MODE=true: Local development using SOCKS5 proxy (localhost:1080)
- LOCAL_MODE=false: GKE Job mode using internal DNS (default)

Prerequisites:
- .env file must contain valid credentials and LOCAL_MODE setting
- For LOCAL_MODE=true: SOCKS5 proxy must be running (run setup_local_proxy.sh)
- For LOCAL_MODE=false: Must run from internal network (GKE Job, bastion, or VM in VPC)
"""

import os
import sys

from common.msqp import create_msqp_client_from_env
from common.utils import get_ingestion_root, get_tenant_dir
from dotenv import load_dotenv
from loguru import logger


def main():
    """Execute sample queries on MSQP using internal endpoints."""
    # Load environment variables from .env file (in ingestion/ directory)
    ingestion_root = get_ingestion_root()
    env_path = ingestion_root / ".env"
    if not env_path.exists():
        logger.error(f".env not found at {env_path}")
        logger.error("Please ensure ingestion/.env file exists with required credentials")
        sys.exit(1)

    load_dotenv(env_path)

    logger.info("=" * 80)
    logger.info("MSQP Sample Query Script")
    logger.info("=" * 80)
    logger.info("")

    # Create MSQP client from environment variables (auto-detects mode)
    try:
        client = create_msqp_client_from_env()
        logger.info("✓ Successfully created MSQP client")
        logger.info("")
    except Exception as e:
        logger.error(f"Failed to create MSQP client: {e}")
        sys.exit(1)

    try:
        logger.info("Use drawing.msqp__drawing")
        client.use(catalog="drawing", schema="msqp__drawing")
    except Exception as e:
        logger.error(f"Initial setup failed: {e}", exc_info=True)
        sys.exit(1)

    try:
        # Example 1: List available tables in current catalog/schema
        logger.info("=" * 80)
        logger.info("Example 1: List Tables in Current Schema")
        logger.info("=" * 80)
        tables = client.list_tables()
        logger.info(f"Found {len(tables)} tables in {client.catalog}.{client.schema}:")
        for i, table in enumerate(tables[:10], 1):
            logger.info(f"  {i}. {table}")
        if len(tables) > 10:
            logger.info(f"  ... and {len(tables) - 10} more tables")
        logger.info("")

        # Example 2: Query a specific table
        if tables:
            target_table = "drawing_page" if "drawing_page" in tables else tables[0]
            logger.info("=" * 80)
            logger.info(f"Example 2: Query Table '{target_table}'")
            logger.info("=" * 80)
            df = client.query(f"SELECT * FROM {target_table} LIMIT 5")
            logger.info(f"Query returned {len(df)} rows")
            logger.info("")
            logger.info("Sample data:")
            logger.info(f"\n{df.to_string()}")
            logger.info("")

            # Example 3: Get table schema
            logger.info("=" * 80)
            logger.info(f"Example 3: Get Schema for Table '{target_table}'")
            logger.info("=" * 80)
            schema_df = client.get_table_schema(target_table)
            logger.info(f"Table has {len(schema_df)} columns:")
            logger.info(f"\n{schema_df.to_string()}")
            logger.info("")

        # Example 4: Load and execute query from query.sql file
        logger.info("=" * 80)
        logger.info("Example 4: Execute Query from query.sql File")
        logger.info("=" * 80)

        # Get tenant directory using common/path.py and load query.sql
        tenant_dir = get_tenant_dir()
        query_file = tenant_dir / "defects" / "query.sql"

        if query_file.exists():
            # Load query template
            query_template = query_file.read_text(encoding="utf-8")
            logger.info(f"Loaded query from: {query_file}")
            logger.info("")

            # Format query with limit parameter
            limit = int(os.getenv("DRAWING_LIMIT", "2"))
            query = query_template.format(limit=limit)

            logger.info("Query:")
            logger.info(query)
            logger.info("")

            # Execute query
            df = client.query(query)
            logger.info(f"Query returned {len(df)} rows")
            logger.info("")
            logger.info("Sample data:")
            logger.info(f"\n{df.to_string()}")
            logger.info("")
        else:
            logger.warning(f"query.sql not found at: {query_file}")
            logger.info("")
    except Exception as e:
        logger.error(f"Query execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
