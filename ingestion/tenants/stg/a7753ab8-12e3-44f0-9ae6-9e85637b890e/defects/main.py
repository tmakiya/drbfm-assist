"""DRBFM Defects Analysis and Ingestion Pipeline."""

import click
from common.pipelines.defects import DefectsPipeline
from common.utils import get_ingestion_root, get_tenant_dir
from dotenv import load_dotenv
from loguru import logger


@click.command()
@click.option("--dry-run", is_flag=True, help="Skip ISP operations")
@click.option("--truncate", is_flag=True, help="Delete and recreate index")
def main(dry_run: bool, truncate: bool) -> None:
    """Execute DRBFM defects analysis and ingestion pipeline."""
    load_dotenv(get_ingestion_root() / ".env")
    pipeline_dir = get_tenant_dir() / "defects"

    # Tenant-specific prompt file path
    # Change this to use a custom prompt file for this tenant
    prompt_file_path = (
        get_ingestion_root() / "common" / "prompts" / "extract_attributes_from_failure_docs.txt"
    )

    pipeline = DefectsPipeline(
        pipeline_dir, dry_run=dry_run, truncate=truncate, prompt_file_path=prompt_file_path
    )
    result = pipeline.run()
    logger.info(result.to_structured_log())


if __name__ == "__main__":
    main()
