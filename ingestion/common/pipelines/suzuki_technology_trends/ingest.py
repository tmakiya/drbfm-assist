"""ISP ingestion helpers for Suzuki Technology Trends."""

import json
import os
from datetime import datetime
from pathlib import Path

import polars as pl
from loguru import logger

from common.isp import create_isp_client_from_env, prepare_documents

from .config import IspConfig


def _save_dry_run_output(
    pipeline_dir: Path,
    index_name: str,
    documents: list[dict],
    mappings: dict,
    settings: dict,
) -> dict:
    """Save dry-run output to JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = pipeline_dir / "dry_run_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"dry_run_documents_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "index_name": index_name,
                "timestamp": timestamp,
                "total_documents": len(documents),
                "mappings": mappings,
                "settings": settings,
                "documents": documents,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info(f"Dry-run output: {output_file}")
    return {
        "index_name": index_name,
        "total": len(documents),
        "success": len(documents),
        "errors": 0,
    }


def ingest_dataframe_to_isp(
    df: pl.DataFrame,
    isp_config: IspConfig,
    pipeline_dir: Path,
    truncate: bool = False,
    dry_run: bool = False,
) -> dict:
    """Ingest suzuki DataFrame to ISP."""
    tenant_id = os.getenv("TENANT_ID")
    if not tenant_id:
        raise ValueError("TENANT_ID environment variable required")

    index_name = f"{isp_config.index_name}_{tenant_id}"
    mappings = isp_config.mappings
    settings = isp_config.settings
    id_field = isp_config.id_field

    logger.info(f"ISP Ingestion: index={index_name}, truncate={truncate}, dry_run={dry_run}")

    # Prepare documents
    documents = prepare_documents(df, isp_config.fields)

    if dry_run:
        return _save_dry_run_output(pipeline_dir, index_name, documents, mappings, settings)

    # Actual ingestion
    client = create_isp_client_from_env()
    client.health_check()

    # Setup index
    client.setup_index(index_name, mappings, settings, truncate=truncate)

    if not truncate:
        drawing_ids = df["drawing_id"].unique().to_list()
        if drawing_ids:
            delete_result = client.delete_by_query(
                index_name,
                {"terms": {isp_config.fields["drawing_id"]: drawing_ids}},
            )
            if delete_result["errors"]:
                logger.warning(
                    "Delete-by-query completed with errors",
                    drawing_ids=len(drawing_ids),
                    total_found=delete_result["total_found"],
                    deleted=delete_result["deleted"],
                    errors=delete_result["errors"],
                )
            else:
                logger.info(
                    "Delete-by-query completed",
                    drawing_ids=len(drawing_ids),
                    total_found=delete_result["total_found"],
                    deleted=delete_result["deleted"],
                )

    # Bulk index
    result = client.bulk_index_documents(index_name, documents, id_field=id_field, upsert=not truncate)

    if result["errors"] > 0:
        logger.error("Errors occurred during bulk indexing")
        for error in result.get("error_details", []):
            logger.error(error)

    logger.info(f"Indexed: {result['success']}/{result['total']} (errors: {result['errors']})")

    return {
        "index_name": index_name,
        "total": result["total"],
        "success": result["success"],
        "errors": result["errors"],
        "error_details": result.get("error_details"),
    }
