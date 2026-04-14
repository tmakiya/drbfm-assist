"""Unit tests for DefectsPipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from common.pipelines.base import PipelineResult
from common.pipelines.defects.pipeline import DefectsPipeline

from tests.mocks.gcs_mock import mock_gcs_client  # noqa: F401

# Import mock fixtures
from tests.mocks.gemini_mock import mock_gemini_client  # noqa: F401
from tests.mocks.isp_mock import mock_isp_client  # noqa: F401
from tests.mocks.msqp_mock import mock_msqp_client  # noqa: F401


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_pipeline_result_to_dict(self) -> None:
        """Test structured representation for serialization."""
        result = PipelineResult(
            success=3,
            errors=1,
            total=4,
            index_name="test-index",
            details={"embedded": 2},
        )

        assert result.to_dict() == {
            "success": 3,
            "errors": 1,
            "total": 4,
            "index_name": "test-index",
            "details": {"embedded": 2},
        }

    def test_pipeline_result_to_structured_log(self) -> None:
        """Test structured log payload."""
        result = PipelineResult(
            success=5,
            errors=0,
            total=5,
            index_name="test-index",
            details={"indexed": 5},
        )

        payload = result.to_structured_log()

        assert payload.startswith("pipeline_result\n")
        assert "index_name=test-index" in payload
        assert "5 / 5 succeeded" in payload
        assert "0 errors" in payload
        assert "details:" in payload
        assert "indexed=5" in payload


class TestDefectsPipelineInit:
    """Tests for DefectsPipeline initialization."""

    def test_init_default_values(
        self,
        temp_config_dir: Path,
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test initialization with default values."""
        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(pipeline_dir=temp_config_dir, prompt_file_path=prompt_file)

        assert pipeline.pipeline_dir == temp_config_dir
        assert pipeline.dry_run is False
        assert pipeline.truncate is False

    def test_init_with_options(
        self,
        temp_config_dir: Path,
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test initialization with options."""
        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(
            pipeline_dir=temp_config_dir,
            dry_run=True,
            truncate=True,
            prompt_file_path=prompt_file,
        )

        assert pipeline.dry_run is True
        assert pipeline.truncate is True

    def test_init_loads_config(
        self,
        temp_config_dir: Path,
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test that config is loaded on initialization."""
        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(pipeline_dir=temp_config_dir, prompt_file_path=prompt_file)

        assert pipeline.config is not None
        assert pipeline.config.image_analysis.model is not None


class TestDefectsPipelineRun:
    """Tests for DefectsPipeline.run method."""

    def test_run_empty_groups_raises(
        self,
        temp_config_dir: Path,
        mock_msqp_client,  # noqa: F811
        mock_gcs_client,  # noqa: F811
        mock_gemini_client,  # noqa: F811
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test that empty groups raises ValueError."""
        # Return empty DataFrame from MSQP
        empty_df = pl.DataFrame(
            {
                "drawing_id": [],
                "original_id": [],
                "page_number": [],
                "file_path": [],
            }
        )
        mock_msqp_client(query_result=empty_df)
        mock_gcs_client()
        mock_gemini_client()

        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(pipeline_dir=temp_config_dir, prompt_file_path=prompt_file)

        with pytest.raises(ValueError, match="No drawings found|No groups"):
            pipeline.run()

    def test_run_no_successful_results_raises(
        self,
        temp_config_dir: Path,
        mock_msqp_client,  # noqa: F811
        mock_gcs_client,  # noqa: F811
        mock_gemini_client,  # noqa: F811
        temp_image_files: list[Path],
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test that no successful analysis raises ValueError."""
        # Return DataFrame with drawings
        drawing_df = pl.DataFrame(
            {
                "drawing_id": ["D1"],
                "original_id": ["O1"],
                "page_number": [1],
                "file_path": ["gs://bucket/path/img1.png"],
            }
        )
        mock_msqp_client(query_result=drawing_df)

        # Mock GCS to return files
        mock_gcs_client(
            bucket_name="bucket",
            blob_configs={"path/img1.png": b"content"},
        )

        # Mock Gemini to fail
        mock_gemini_client(generate_error=Exception("API Error"))

        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(pipeline_dir=temp_config_dir, prompt_file_path=prompt_file)

        with pytest.raises(ValueError, match="No successful|No valid"):
            pipeline.run()

    @patch("common.pipelines.defects.pipeline.fetch_drawings")
    @patch("common.pipelines.defects.pipeline.group_drawings_by_original_id")
    @patch("common.pipelines.defects.pipeline.analyze_groups_parallel")
    @patch("common.pipelines.defects.pipeline.build_dataframe_with_embeddings")
    @patch("common.pipelines.defects.pipeline.ingest_dataframe_to_isp")
    def test_run_success(
        self,
        mock_ingest: MagicMock,
        mock_build_df: MagicMock,
        mock_analyze: MagicMock,
        mock_group: MagicMock,
        mock_fetch: MagicMock,
        temp_config_dir: Path,
        mock_gemini_client,  # noqa: F811
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test successful pipeline execution."""
        mock_gemini_client()

        # Mock fetch_drawings
        mock_fetch.return_value = pl.DataFrame(
            {
                "drawing_id": ["D1", "D2"],
                "original_id": ["O1", "O1"],
                "page_number": [1, 2],
                "local_path": ["/tmp/img1.png", "/tmp/img2.png"],
            }
        )

        # Mock group_drawings_by_original_id
        mock_group.return_value = [
            {"original_id": "O1", "image_paths": [], "drawing_ids": ["D1", "D2"]},
        ]

        # Mock analyze_groups_parallel
        mock_analyze.return_value = (
            pl.DataFrame({"original_id": ["O1"]}),
            {
                "success": 1,
                "skipped_large_file": 0,
                "image_analysis_error": 0,
                "total_groups": 1,
            },
        )

        # Mock build_dataframe_with_embeddings
        mock_build_df.return_value = (
            pl.DataFrame({"doc_id": [1], "original_id": ["O1"]}),
            {
                "embedded": 1,
                "embedding_error": 0,
                "total_records": 1,
            },
        )

        # Mock ingest_dataframe_to_isp
        mock_ingest.return_value = {
            "index_name": "test-index",
            "success": 1,
            "errors": 0,
        }

        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(pipeline_dir=temp_config_dir, prompt_file_path=prompt_file)
        result = pipeline.run()

        assert isinstance(result, PipelineResult)
        assert result.success == 1
        assert result.errors == 0
        assert result.index_name == "test-index"

    @patch("common.pipelines.defects.pipeline.fetch_drawings")
    @patch("common.pipelines.defects.pipeline.group_drawings_by_original_id")
    @patch("common.pipelines.defects.pipeline.analyze_groups_parallel")
    @patch("common.pipelines.defects.pipeline.build_dataframe_with_embeddings")
    @patch("common.pipelines.defects.pipeline.ingest_dataframe_to_isp")
    def test_run_with_partial_errors(
        self,
        mock_ingest: MagicMock,
        mock_build_df: MagicMock,
        mock_analyze: MagicMock,
        mock_group: MagicMock,
        mock_fetch: MagicMock,
        temp_config_dir: Path,
        mock_gemini_client,  # noqa: F811
        mock_env_pipeline: dict[str, str],
    ) -> None:
        """Test pipeline execution with partial errors."""
        mock_gemini_client()

        # Mock fetch_drawings
        mock_fetch.return_value = pl.DataFrame(
            {
                "drawing_id": ["D1", "D2", "D3"],
                "original_id": ["O1", "O2", "O3"],
                "page_number": [1, 1, 1],
                "local_path": ["/tmp/img1.png", "/tmp/img2.png", "/tmp/img3.png"],
            }
        )

        # Mock group_drawings_by_original_id
        mock_group.return_value = [
            {"original_id": "O1", "image_paths": [], "drawing_ids": ["D1"]},
            {"original_id": "O2", "image_paths": [], "drawing_ids": ["D2"]},
            {"original_id": "O3", "image_paths": [], "drawing_ids": ["D3"]},
        ]

        # Mock analyze_groups_parallel - 2 success, 1 large file skipped
        mock_analyze.return_value = (
            pl.DataFrame({"original_id": ["O1", "O2"]}),
            {
                "success": 2,
                "skipped_large_file": 1,
                "image_analysis_error": 0,
                "total_groups": 3,
            },
        )

        # Mock build_dataframe_with_embeddings
        mock_build_df.return_value = (
            pl.DataFrame({"doc_id": [1, 2], "original_id": ["O1", "O2"]}),
            {
                "embedded": 2,
                "embedding_error": 0,
                "total_records": 2,
            },
        )

        # Mock ingest_dataframe_to_isp
        mock_ingest.return_value = {
            "index_name": "test-index",
            "success": 2,
            "errors": 0,
        }

        prompt_file = temp_config_dir / "prompt.txt"
        pipeline = DefectsPipeline(pipeline_dir=temp_config_dir, prompt_file_path=prompt_file)
        result = pipeline.run()

        assert result.success == 2
        assert result.errors == 1  # 1 skipped
        assert result.total == 3
        assert result.details["skipped_large_file"] == 1
