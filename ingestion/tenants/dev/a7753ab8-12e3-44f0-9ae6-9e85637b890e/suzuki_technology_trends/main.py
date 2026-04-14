"""Suzuki Technology Trends Ingestion Pipeline."""

from pathlib import Path

import click
import polars as pl
from common.pipelines.suzuki_technology_trends import (
    SuzukiTechnologyTrendsPipeline,
)
from common.utils import get_ingestion_root, get_tenant_dir
from dotenv import load_dotenv
from loguru import logger


def get_csv_total_row_count(pipeline_dir: Path) -> int:
    """Get total row count from CSV file.

    Args:
        pipeline_dir: Directory containing test_data.csv

    Returns:
        Total number of rows in the CSV file

    """
    csv_path = pipeline_dir / "test_data.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logger.info("Getting total row count from CSV...")

    # Count lines efficiently without loading entire file into memory
    with open(csv_path, encoding="utf-8") as f:
        # Skip header
        next(f)
        total_rows = sum(1 for _ in f)

    logger.info(f"Total rows in CSV: {total_rows:,}")
    return total_rows


def load_csv_data(
    pipeline_dir: Path,
    batch_size: int | None = None,
    offset: int = 0,
) -> pl.DataFrame:
    """Load suzuki-technology-trends CSV data.

    Args:
        pipeline_dir: Directory containing test_data.csv
        batch_size: Number of rows to fetch (for pagination). If None, fetch all.
        offset: Number of rows to skip (for pagination)

    Returns:
        Polars DataFrame with CSV data

    """
    csv_path = pipeline_dir / "test_data.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Load CSV with Polars, with pagination support
    if batch_size is not None:
        # Skip header + offset rows, read batch_size rows
        df = pl.read_csv(csv_path, skip_rows=offset, n_rows=batch_size)
    else:
        df = pl.read_csv(csv_path)

    logger.info(f"Loaded {len(df)} rows from {csv_path.name} (offset={offset}, batch_size={batch_size})")
    logger.debug(f"Columns: {df.columns}")

    return df


@click.command()
@click.option("--dry-run", is_flag=True, help="Skip ISP operations")
@click.option("--truncate", is_flag=True, help="Delete and recreate index")
def main(dry_run: bool, truncate: bool) -> None:
    """Execute Suzuki Technology Trends ingestion pipeline with micro-batching."""
    load_dotenv(get_ingestion_root() / ".env")
    pipeline_dir = get_tenant_dir() / "suzuki_technology_trends"

    # Get actual total row count from CSV
    total_rows_in_csv = get_csv_total_row_count(pipeline_dir)

    def load_batch(batch_size: int, offset: int) -> pl.DataFrame:
        return load_csv_data(pipeline_dir, batch_size=batch_size, offset=offset)

    pipeline = SuzukiTechnologyTrendsPipeline(
        pipeline_dir,
        load_batch=load_batch,
        total_rows=total_rows_in_csv,
        dry_run=dry_run,
        truncate=truncate,
    )
    result = pipeline.run()
    logger.info(result.to_structured_log())


if __name__ == "__main__":
    main()
