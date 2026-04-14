"""Shared Suzuki Technology Trends pipeline runner."""

import gc
from collections.abc import Callable
from pathlib import Path

import polars as pl
from loguru import logger

from common.utils import (
    BatchContext,
    add_doc_id_from_fields,
    explode_rows_by_text_chunks,
    run_batch_processing,
)

from ..base import BasePipeline, PipelineResult
from .config import PipelineConfig
from .ingest import ingest_dataframe_to_isp
from .processing import add_embeddings, split_theme_columns

LoadBatchFn = Callable[[int, int], pl.DataFrame]


class SuzukiTechnologyTrendsPipeline(BasePipeline):
    """Pipeline runner for Suzuki Technology Trends."""

    def __init__(
        self,
        pipeline_dir: Path,
        load_batch: LoadBatchFn,
        total_rows: int,
        dry_run: bool = False,
        truncate: bool = False,
    ) -> None:
        """Initialize the pipeline runner.

        Args:
            pipeline_dir: Directory containing pipeline configuration files
            load_batch: Callable that loads a batch by (batch_size, offset)
            total_rows: Total number of available rows
            dry_run: If True, skip ISP operations
            truncate: If True, delete and recreate index on first batch

        """
        super().__init__(pipeline_dir, dry_run=dry_run, truncate=truncate)
        self.config = PipelineConfig.from_dir(pipeline_dir)
        self.load_batch = load_batch
        self.total_rows = total_rows

    def run(self) -> PipelineResult:
        """Execute the pipeline."""
        logger.info(
            "Starting pipeline "
            f"(batch_size={self.config.batch_size}, total_rows={self.total_rows:,}, dry_run={self.dry_run})"
        )

        overall_stats = run_batch_processing(
            total_rows=self.total_rows,
            batch_size=self.config.batch_size,
            truncate=self.truncate,
            dry_run=self.dry_run,
            batch_fn=self._process_batch,
        )

        return PipelineResult(
            success=overall_stats.get("success", 0),
            errors=overall_stats.get("errors", 0),
            total=overall_stats.get("total", 0),
            index_name=f"{self.config.isp.index_name}_{self.config.tenant_id}",
            details={
                "batches_completed": overall_stats.get("batches_completed", 0),
                "batches_failed": overall_stats.get("batches_failed", 0),
                "batch_size": overall_stats.get("batch_size", 0),
                "num_batches": overall_stats.get("num_batches", 0),
            },
        )

    def _process_batch(self, context: BatchContext) -> dict:
        """Process a single batch."""
        logger.info(
            f"=== Processing Batch {context.batch_num} "
            f"(offset={context.offset}, batch_size={context.batch_size}) ==="
        )

        # Step 1: Load data
        df = self.load_batch(context.batch_size, context.offset)
        if len(df) == 0:
            logger.warning(f"Batch {context.batch_num}: No data loaded, skipping")
            return {"success": 0, "total": 0, "errors": 0}

        # step 2: Split theme columns
        df = split_theme_columns(df)

        # step 3: Explode rows by text chunks(add field [chunk_id, total_chunks])
        df = explode_rows_by_text_chunks(
            df,
            source_field=self.config.embedding.source_field,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )

        # Step 4: Add embeddings and ingest
        df = add_embeddings(df, self.config.embedding)

        # Step 5: Generate doc_ids
        df = add_doc_id_from_fields(df, ["drawing_id", "chunk_id"])

        # Step 6: Ingest to ISP
        result = ingest_dataframe_to_isp(
            df,
            self.config.isp,
            pipeline_dir=self.config.pipeline_dir,
            truncate=context.truncate,
            dry_run=context.dry_run,
        )

        logger.info(
            f"Batch {context.batch_num} completed: {result['success']}/{result['total']} succeeded, "
            f"{result['errors']} errors"
        )

        del df
        gc.collect()

        return result
