"""Drawing fetching functionality for defects pipeline."""

import os

import polars as pl
from loguru import logger

from common.gcs import download_from_dataframe
from common.msqp import create_msqp_client_from_env

from .config import PipelineConfig


def fetch_drawings(config: PipelineConfig) -> pl.DataFrame:
    """Query MSQP for drawings and download images from GCS.

    Args:
        config: Pipeline configuration

    Returns:
        DataFrame with drawing data and local file paths

    Raises:
        ValueError: If no drawings found or no valid file paths

    """
    # Query MSQP
    msqp_client = create_msqp_client_from_env()
    msqp_client.use(catalog="drawing", schema="msqp__drawing")

    query_template = (config.pipeline_dir / "query.sql").read_text(encoding="utf-8")

    limit = int(os.getenv("QUERY_FILE_LIMIT", "100000"))
    df = msqp_client.query(query_template.format(limit=limit))

    logger.debug(f"MSQP query returned DataFrame with shape: {df.shape}, height: {df.height}")

    if df.height == 0:
        raise ValueError("No drawings found in MSQP")

    # Remove duplicate columns (keep first occurrence)
    seen = set()
    unique_cols = []
    for col in df.columns:
        if col not in seen:
            seen.add(col)
            unique_cols.append(col)
    df = df.select(unique_cols)
    logger.info(f"Found {len(df)} drawings")

    # Download images from GCS
    df = download_from_dataframe(
        df=df,
        gcs_path_column="file_path",
        data_dir=config.data_dir,
        bucket_name=config.bucket_name,
        max_workers=4,
    )

    if df.is_empty():
        raise ValueError("No valid file paths found")

    logger.info(f"Downloaded {len(df)} images")
    return df
