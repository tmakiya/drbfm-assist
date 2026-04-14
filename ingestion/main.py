"""Main entrypoint for DRBFM ingestion Kubernetes Job.

This script executes tenant-specific ingestion pipelines.

Architecture:
    ingestion/main.py (this file)
      -> tenants/{env}/{tenant_id}/main.py
         -> defects/main.py
         -> [other pipelines...]

Usage:
    python main.py --env dev --tenant-id a7753ab8-12e3-44f0-9ae6-9e85637b890e
"""

import argparse
import importlib.util
import os
import sys

import requests
from common.utils import get_ingestion_root
from dotenv import load_dotenv
from loguru import logger

# Setup
INGESTION_ROOT = get_ingestion_root()

# Load .env file
if (INGESTION_ROOT / ".env").exists():
    load_dotenv(INGESTION_ROOT / ".env")


def execute_tenant_main(env: str, tenant_id: str, pipeline: str = None, dry_run: bool = False) -> None:
    """Load and execute tenant-specific main.py.

    Args:
        env: Environment (dev, stg, prod)
        tenant_id: Tenant ID
        pipeline: Optional pipeline name to execute (executes all if not specified)
        dry_run: If True, run pipelines in dry-run mode

    """
    # Validate inputs
    if env not in ["dev", "stg", "prod"]:
        raise ValueError(f"Invalid environment: {env}")

    tenant_dir = INGESTION_ROOT / "tenants" / env / tenant_id
    tenant_main_path = tenant_dir / "main.py"

    if not tenant_main_path.exists():
        raise FileNotFoundError(f"Tenant main.py not found: {tenant_main_path}")

    # Validate required env vars
    required_vars = ["MSQP_CLIENT_ID", "MSQP_CLIENT_SECRET"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

    logger.info(f"Environment: {env}")
    logger.info(f"Tenant ID: {tenant_id}")
    if pipeline:
        logger.info(f"Pipeline: {pipeline} (only)")
    logger.info(f"Tenant main: {tenant_main_path}")
    logger.info("")

    # Add tenant directory to Python path so imports work
    sys.path.insert(0, str(tenant_dir))

    # Load and execute tenant main
    spec = importlib.util.spec_from_file_location("tenant_main", tenant_main_path)
    if not spec or not spec.loader:
        raise ImportError(f"Failed to load: {tenant_main_path}")

    tenant_module = importlib.util.module_from_spec(spec)
    sys.modules["tenant_main"] = tenant_module
    spec.loader.exec_module(tenant_module)

    if not hasattr(tenant_module, "main"):
        raise AttributeError(f"No main() function in: {tenant_main_path}")

    # Call main with pipeline argument
    tenant_module.main(pipeline=pipeline, dry_run=dry_run)


def shutdown_istio_sidecar() -> None:
    """Send shutdown signal to Istio sidecar if present.

    This ensures the sidecar terminates gracefully when the main application completes,
    allowing Kubernetes Jobs to finish properly.
    """
    try:
        response = requests.post(
            "http://localhost:15020/quitquitquit",
            timeout=5,
        )
        if response.status_code == 200:
            logger.info("Istio sidecar shutdown signal sent successfully")
        else:
            logger.warning(f"Istio sidecar responded with status {response.status_code}")
    except requests.exceptions.ConnectionError:
        logger.debug("Istio sidecar not found (connection refused) - likely not running in Istio mesh")
    except requests.exceptions.Timeout:
        logger.warning("Timeout sending shutdown signal to Istio sidecar")
    except Exception as e:
        logger.debug(f"Could not signal Istio sidecar: {e}")


def main():
    """Run main ingestion job."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="DRBFM Ingestion Job")
    parser.add_argument("--env", required=True, choices=["dev", "stg", "prod"], help="Environment")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID")
    parser.add_argument("--pipeline", help="Specific pipeline to execute (default: all)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Run pipelines in dry-run mode")
    mode.add_argument("--validate-only", action="store_true", help="Validate tenant entrypoint only")
    args = parser.parse_args()

    try:
        logger.info("=" * 80)
        logger.info("DRBFM Ingestion Job")
        logger.info("=" * 80)

        if args.validate_only:
            # Validate tenant entrypoint only
            tenant_main = INGESTION_ROOT / "tenants" / args.env / args.tenant_id / "main.py"
            if not tenant_main.exists():
                raise FileNotFoundError(f"Not found: {tenant_main}")
            logger.info("Validation completed successfully")
        else:
            # Execute
            execute_tenant_main(
                args.env,
                args.tenant_id,
                args.pipeline,
                dry_run=args.dry_run,
            )
            logger.info("")
            logger.info("=" * 80)
            logger.info("INGESTION JOB COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"INGESTION JOB FAILED: {e}", exc_info=True)
        logger.error("=" * 80)
        sys.exit(1)
    finally:
        # Shutdown Istio sidecar to allow Kubernetes Job to complete
        shutdown_istio_sidecar()


if __name__ == "__main__":
    main()
