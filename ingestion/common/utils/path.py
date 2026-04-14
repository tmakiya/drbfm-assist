"""Path utilities for tenant directory resolution."""

import os
from pathlib import Path


def get_ingestion_root() -> Path:
    """Get ingestion root directory.

    Path(__file__) refers to this file's path:
        - Local: path-to-repo/drbfm-assist/ingestion/common/utils/path.py
        - Container: /app/common/utils/path.py

    Returns:
        Path: ingestion root directory
            - Local: path-to-repo/drbfm-assist/ingestion/
            - Container: /app/

    """
    return Path(__file__).parent.parent.parent


def get_tenant_dir() -> Path:
    """Get tenant directory from ENV and TENANT_ID environment variables."""
    env = os.getenv("ENV")
    tenant_id = os.getenv("TENANT_ID")

    if not env:
        raise ValueError("ENV environment variable is not set")
    if not tenant_id:
        raise ValueError("TENANT_ID environment variable is not set")

    return get_ingestion_root() / "tenants" / env / tenant_id
