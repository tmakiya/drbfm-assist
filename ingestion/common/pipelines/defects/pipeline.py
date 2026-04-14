"""Defects pipeline implementation."""

from pathlib import Path

from loguru import logger

from common.utils import add_doc_id_from_fields

from ..base import BasePipeline, PipelineResult
from .config import PipelineConfig
from .fetching import fetch_drawings
from .ingest import ingest_dataframe_to_isp
from .processing import (
    analyze_groups_parallel,
    build_dataframe_with_embeddings,
    group_drawings_by_original_id,
)


class DefectsPipeline(BasePipeline):
    """Defects analysis and ingestion pipeline."""

    def __init__(
        self,
        pipeline_dir: Path,
        prompt_file_path: Path,
        dry_run: bool = False,
        truncate: bool = False,
    ):
        """Initialize the defects pipeline.

        Args:
            pipeline_dir: Directory containing pipeline configuration files
            prompt_file_path: Path to the prompt file. If None, uses default
            dry_run: If True, skip actual ingestion operations
            truncate: If True, delete and recreate the index

        """
        super().__init__(pipeline_dir, dry_run, truncate)
        self.config = PipelineConfig.from_dir(pipeline_dir, prompt_file_path)

    def run(self) -> PipelineResult:
        """Execute the defects pipeline."""
        logger.info(f"Starting pipeline(model={self.config.image_analysis.model}, dry_run={self.dry_run})")

        # step1: Fetch and group drawings
        drawing_df = fetch_drawings(self.config)

        # step2: Group drawings by original_id
        groups = group_drawings_by_original_id(drawing_df)

        if not groups:
            raise ValueError("No groups to process")

        # step3: Analyze images
        logger.info(f"Analyzing {len(groups)} groups...")
        success_df, analysis_summary = analyze_groups_parallel(
            groups=groups,
            image_analysis_config=self.config.image_analysis,
        )

        if analysis_summary.get("success", 0) == 0:
            raise ValueError("No successful analysis results")

        # step4: Build embeddings
        df, embedding_summary = build_dataframe_with_embeddings(
            success_df,
            embedding_config=self.config.embedding,
        )

        if df.is_empty():
            raise ValueError("No data to ingest")

        # step5: Add doc_id
        df = add_doc_id_from_fields(df, ["original_id"])

        # step6: Ingest to ISP
        ingest_summary = ingest_dataframe_to_isp(
            df,
            isp_config=self.config.isp,
            pipeline_dir=self.config.pipeline_dir,
            truncate=self.truncate,
            dry_run=self.dry_run,
        )

        # Summarize
        total_errors = (
            analysis_summary.get("skipped_large_file", 0)
            + analysis_summary.get("image_analysis_error", 0)
            + embedding_summary.get("embedding_error", 0)
            + ingest_summary.get("errors", 0)
        )

        return PipelineResult(
            success=ingest_summary.get("success", 0),
            errors=total_errors,
            total=analysis_summary.get("total_groups", 0),
            index_name=ingest_summary.get("index_name"),
            details={
                "analysis_success": analysis_summary.get("success", 0),
                "total_groups": analysis_summary.get("total_groups", 0),
                "skipped_large_file": analysis_summary.get("skipped_large_file", 0),
                "image_analysis_error": analysis_summary.get("image_analysis_error", 0),
                "embedded": embedding_summary.get("embedded", 0),
                "embedding_skipped_empty": embedding_summary.get("embedding_skipped_empty", 0),
                "embedding_error": embedding_summary.get("embedding_error", 0),
                "indexed": ingest_summary.get("success", 0),
                "index_errors": ingest_summary.get("errors", 0),
            },
        )
