"""BigQuery helpers for ingestion pipelines."""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from google.cloud import bigquery
from loguru import logger


def get_total_row_count(client: bigquery.Client, table_fqn: str) -> int:
    """Get total row count from a BigQuery table."""
    count_query = f"""
    SELECT COUNT(*) as total
    FROM `{table_fqn}`
    """

    logger.info("Getting total row count from BigQuery...")
    query_job = client.query(count_query)
    result = list(query_job.result())
    total_rows = result[0]["total"]

    logger.info(f"Total rows in table: {total_rows:,}")
    return total_rows


def resolve_query_limit(batch_size: int | None) -> int:
    """Resolve the query limit for micro-batch processing."""
    if batch_size is not None:
        limit = batch_size
    else:
        limit = int(os.getenv("QUERY_FILE_LIMIT", "100000"))
    return limit


def build_micro_batch_query(
    query_template: str,
    template_vars: dict[str, str],
    batch_size: int | None,
    offset: int,
) -> str:
    """Build a query with limit/offset applied to a formatted template."""
    query = query_template.format(**template_vars)

    limit = resolve_query_limit(batch_size)
    if limit > 0:
        query = f"{query}\nLIMIT {limit}"

    if offset > 0:
        query = f"{query}\nOFFSET {offset}"

    return query


def load_bigquery_data(
    query: str,
    client: bigquery.Client,
) -> pl.DataFrame:
    """Load data from BigQuery using a provided query."""
    logger.info("Executing BigQuery query")
    logger.info(f"Query:\n{query[:1000]}")
    query_job = client.query(query)

    arrow_table = query_job.to_arrow()
    df = pl.from_arrow(arrow_table)

    logger.info(f"Loaded {len(df)} rows from BigQuery")
    logger.debug(f"Columns: {df.columns}")

    return df


def load_bigquery_micro_batch(
    pipeline_dir: Path,
    client: bigquery.Client,
    template_vars: dict[str, str],
    batch_size: int | None = None,
    offset: int = 0,
) -> pl.DataFrame:
    """Load micro-batch data from BigQuery using template variables."""
    query_path = pipeline_dir / "query.sql"
    if not query_path.exists():
        raise FileNotFoundError(f"Query file not found: {query_path}")

    query_template = query_path.read_text(encoding="utf-8")
    query = build_micro_batch_query(query_template, template_vars, batch_size, offset)
    logger.debug(f"Built BigQuery query (offset={offset})")

    return load_bigquery_data(query, client)
