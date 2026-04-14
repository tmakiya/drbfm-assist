"""Suzuki Technology Trends Ingestion Pipeline."""

import click
import polars as pl
from common.bigquery import (
    get_total_row_count,
    load_bigquery_micro_batch,
)
from common.pipelines.suzuki_technology_trends import (
    PipelineConfig,
    SuzukiTechnologyTrendsPipeline,
)
from common.utils import get_ingestion_root, get_tenant_dir
from dotenv import load_dotenv
from google.cloud import bigquery
from loguru import logger


@click.command()
@click.option("--dry-run", is_flag=True, help="Skip ISP operations")
@click.option("--truncate", is_flag=True, help="Delete and recreate index")
def main(dry_run: bool, truncate: bool) -> None:
    """Execute Suzuki Technology Trends ingestion pipeline with micro-batching."""
    load_dotenv(get_ingestion_root() / ".env")
    pipeline_dir = get_tenant_dir() / "suzuki_technology_trends"

    # Load configuration
    config = PipelineConfig.from_dir(pipeline_dir)

    template_vars = {"table_fqn": config.table_fqn}
    bq_client = bigquery.Client(project=config.bq_project)

    # Get actual total row count from BigQuery
    total_rows = get_total_row_count(bq_client, config.table_fqn)

    def load_batch(batch_size: int, offset: int) -> pl.DataFrame:
        return load_bigquery_micro_batch(
            pipeline_dir,
            bq_client,
            template_vars,
            batch_size=batch_size,
            offset=offset,
        )

    pipeline = SuzukiTechnologyTrendsPipeline(
        pipeline_dir,
        load_batch=load_batch,
        total_rows=total_rows,
        dry_run=dry_run,
        truncate=truncate,
    )
    result = pipeline.run()
    logger.info(result.to_structured_log())


if __name__ == "__main__":
    main()
