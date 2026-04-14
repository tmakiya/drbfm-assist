"""Tenant-level ingestion orchestrator

Executes ingestion pipelines in order:
  1. defects/main.py - DRBFM defects analysis
  (Add more pipelines here as needed)
"""

import sys
from pathlib import Path

# Import pipeline main functions
from defects.main import main as defects
from loguru import logger

# Define pipelines to execute (name, function)
target_pipelines = [
    ("defects", defects),
]


def main(pipeline: str = None, dry_run: bool = False):
    """Execute all ingestion pipelines for this tenant.

    Args:
        pipeline: Optional pipeline name to execute (executes all if not specified)
        dry_run: If True, run pipelines in dry-run mode

    """
    logger.info("=" * 80)
    logger.info(f"Tenant Ingestion: {Path.cwd().parent.name}")
    logger.info("=" * 80)

    # Filter pipelines if specified
    if pipeline:
        pipelines_to_run = [(name, func) for name, func in target_pipelines if name == pipeline]
    else:
        pipelines_to_run = target_pipelines

    logger.info(f"Pipelines to execute: {len(pipelines_to_run)}")
    logger.info("")

    # Execute each pipeline in order
    for i, (pipeline_name, pipeline_func) in enumerate(pipelines_to_run, 1):
        logger.info("=" * 80)
        logger.info(f"[{i}/{len(pipelines_to_run)}] Executing Pipeline: {pipeline_name}")
        logger.info("=" * 80)

        # reset sys.argv to prevent interference with imported modules
        sys.argv = [""]

        try:
            pipeline_args = ["--dry-run"] if dry_run else []
            pipeline_func.main(args=pipeline_args, standalone_mode=False)
        except Exception as e:
            logger.error(f"Pipeline '{pipeline_name}' failed with error: {e}")
            sys.exit(1)

        logger.info("")

    logger.info("=" * 80)
    logger.info(f"All {len(pipelines_to_run)} pipelines completed successfully")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
