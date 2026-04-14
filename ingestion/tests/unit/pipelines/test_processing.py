"""Unit tests for defects pipeline processing module."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest
from common.pipelines.defects.config import EmbeddingConfig
from common.pipelines.defects.processing import (
    _create_record_from_result,
    _process_single_group,
    build_dataframe_with_embeddings,
    group_drawings_by_original_id,
)

# Import mock fixtures
from tests.mocks.gemini_mock import mock_gemini_client  # noqa: F401


@pytest.fixture
def embedding_config() -> EmbeddingConfig:
    """Embedding config for tests."""
    return EmbeddingConfig(
        model="text-embedding-004",
        source_field="cause_unit",
        task_type="RETRIEVAL_DOCUMENT",
        dimensionality=768,
    )


@pytest.fixture
def success_records_df(sample_analysis_results: list[dict[str, Any]]) -> pl.DataFrame:
    """DataFrame built from successful analysis results."""
    records = [
        _create_record_from_result(result)
        for result in sample_analysis_results
        if result.get("status") == "success"
    ]
    return pl.DataFrame(records)


class TestGroupDrawingsByOriginalId:
    """Tests for group_drawings_by_original_id function."""

    def test_groups_by_original_id(self, temp_image_files: list[Path]) -> None:
        """Test that drawings are grouped correctly by original_id."""
        df = pl.DataFrame(
            {
                "drawing_id": ["D1", "D2", "D3"],
                "original_id": ["O1", "O1", "O2"],
                "page_number": [1, 2, 1],
                "local_path": [str(p) for p in temp_image_files],
            }
        )

        groups = group_drawings_by_original_id(df)

        assert len(groups) == 2

        # Find O1 group
        o1_group = next(g for g in groups if g["original_id"] == "O1")
        assert len(o1_group["image_paths"]) == 2
        assert o1_group["drawing_ids"] == ["D1", "D2"]
        assert o1_group["page_count"] == 2

        # Find O2 group
        o2_group = next(g for g in groups if g["original_id"] == "O2")
        assert len(o2_group["image_paths"]) == 1
        assert o2_group["drawing_ids"] == ["D3"]

    def test_sorts_by_page_number(self, temp_image_files: list[Path]) -> None:
        """Test that pages are sorted by page_number within each group."""
        df = pl.DataFrame(
            {
                "drawing_id": ["D2", "D1", "D3"],  # Out of order by drawing_id
                "original_id": ["O1", "O1", "O1"],
                "page_number": [2, 1, 3],  # Out of order
                "local_path": [str(temp_image_files[1]), str(temp_image_files[0]), str(temp_image_files[2])],
            }
        )

        groups = group_drawings_by_original_id(df)

        assert len(groups) == 1
        # Should be sorted by page_number
        assert groups[0]["drawing_ids"] == ["D1", "D2", "D3"]

    def test_skips_missing_files(self, tmp_path: Path, temp_image_files: list[Path]) -> None:
        """Test that missing files are skipped."""
        df = pl.DataFrame(
            {
                "drawing_id": ["D1", "D2"],
                "original_id": ["O1", "O1"],
                "page_number": [1, 2],
                "local_path": [
                    str(temp_image_files[0]),  # Exists
                    str(tmp_path / "nonexistent.png"),  # Does not exist
                ],
            }
        )

        groups = group_drawings_by_original_id(df)

        assert len(groups) == 1
        assert len(groups[0]["image_paths"]) == 1
        assert groups[0]["drawing_ids"] == ["D1"]

    def test_empty_dataframe(self) -> None:
        """Test grouping with empty DataFrame."""
        df = pl.DataFrame(
            {
                "drawing_id": [],
                "original_id": [],
                "page_number": [],
                "local_path": [],
            }
        )

        groups = group_drawings_by_original_id(df)

        assert groups == []

    def test_all_files_missing_returns_empty_groups(self, tmp_path: Path) -> None:
        """Test that groups with all missing files are excluded."""
        df = pl.DataFrame(
            {
                "drawing_id": ["D1", "D2"],
                "original_id": ["O1", "O1"],
                "page_number": [1, 2],
                "local_path": [
                    str(tmp_path / "missing1.png"),
                    str(tmp_path / "missing2.png"),
                ],
            }
        )

        groups = group_drawings_by_original_id(df)

        assert groups == []


class TestCreateRecordFromResult:
    """Tests for _create_record_from_result function."""

    def test_create_record_success(
        self,
        sample_analysis_results: list[dict[str, Any]],
    ) -> None:
        """Test creating record from successful result."""
        result = sample_analysis_results[0]

        record = _create_record_from_result(result)

        assert record["original_id"] == "ORG001"
        assert record["cause_unit"] == "テストユニット1"
        assert record["failure_mode"] == "摩耗"
        assert "doc_id" not in record


class TestBuildDataframeWithEmbeddings:
    """Tests for build_dataframe_with_embeddings function."""

    def test_builds_dataframe_from_results(
        self,
        mock_gemini_client,  # noqa: F811
        success_records_df: pl.DataFrame,
        embedding_config: EmbeddingConfig,
    ) -> None:
        """Test DataFrame construction from analysis results."""
        mock_gemini_client(embed_response=[[0.1] * 768, [0.2] * 768])

        df, summary = build_dataframe_with_embeddings(
            success_records_df,
            embedding_config=embedding_config,
        )

        assert len(df) == 2
        assert "embedding" in df.columns
        assert "original_id" in df.columns
        assert summary["embedded"] == 2
        assert summary["embedding_error"] == 0
        assert summary["embedding_skipped_empty"] == 0
        assert summary["total_records"] == 2

    def test_filters_non_success_results(
        self,
        mock_gemini_client,  # noqa: F811
        success_records_df: pl.DataFrame,
        embedding_config: EmbeddingConfig,
    ) -> None:
        """Test that successful records are embedded."""
        mock_gemini_client(embed_response=[[0.1] * 768, [0.2] * 768])

        df, summary = build_dataframe_with_embeddings(
            success_records_df,
            embedding_config=embedding_config,
        )

        # Only 2 successful results should be in DataFrame
        assert len(df) == 2
        assert summary["embedded"] == 2
        assert summary["embedding_skipped_empty"] == 0

    def test_no_successful_results_returns_empty(
        self,
        mock_gemini_client,  # noqa: F811
        embedding_config: EmbeddingConfig,
    ) -> None:
        """Test that no successful results returns empty DataFrame."""
        mock_gemini_client()

        df, summary = build_dataframe_with_embeddings(
            pl.DataFrame(),
            embedding_config=embedding_config,
        )

        assert df.is_empty()
        assert summary["embedded"] == 0
        assert summary["embedding_error"] == 0
        assert summary["embedding_skipped_empty"] == 0
        assert summary["total_records"] == 0

    def test_embedding_error_returns_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        success_records_df: pl.DataFrame,
        embedding_config: EmbeddingConfig,
    ) -> None:
        """Test that embedding errors are captured."""
        # Patch generate_embeddings_batch to raise an exception
        from unittest.mock import patch

        with patch(
            "common.pipelines.defects.processing.generate_embeddings_batch",
            side_effect=Exception("Embedding API error"),
        ):
            df, summary = build_dataframe_with_embeddings(
                success_records_df,
                embedding_config=embedding_config,
            )

        assert df.is_empty()
        assert summary["embedded"] == 0
        assert summary["embedding_error"] == 2
        assert summary["embedding_skipped_empty"] == 0
        assert summary["total_records"] == 2


class TestProcessSingleGroup:
    """Tests for _process_single_group function."""

    def test_process_success(
        self,
        mock_gemini_client,  # noqa: F811
        temp_image_files: list[Path],
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test successful group processing."""
        expected_response = {
            "cause_unit": "テストユニット1",
            "failure_mode": "摩耗",
        }
        mock_gemini_client(generate_response=expected_response)

        group = {
            "original_id": "ORG001",
            "image_paths": temp_image_files[:2],
            "drawing_ids": ["D1", "D2"],
            "page_count": 2,
        }

        from common.gemini import GeminiClient

        client = GeminiClient(model_name="gemini-2.0-flash")

        result = _process_single_group(
            group=group,
            system_instruction="Analyze",
            response_schema=sample_response_schema,
            model_name="gemini-2.0-flash",
            client=client,
        )

        assert result["status"] == "success"
        assert result["original_id"] == "ORG001"
        assert result["page_count"] == 2

    def test_process_large_file_skipped(
        self,
        mock_gemini_client,  # noqa: F811
        tmp_path: Path,
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test that large files are skipped."""
        mock_gemini_client()

        # Create a large file (simulate with stat mocking)
        large_file = tmp_path / "large.png"
        large_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        group = {
            "original_id": "ORG001",
            "image_paths": [large_file],
            "drawing_ids": ["D1"],
            "page_count": 1,
        }

        from unittest.mock import patch

        # Mock file size to exceed 50MB
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 60 * 1024 * 1024  # 60MB

            result = _process_single_group(
                group=group,
                system_instruction="Analyze",
                response_schema=sample_response_schema,
                model_name="gemini-2.0-flash",
            )

        assert result["status"] == "skipped_large_file"
        assert "50MB" in result["error_detail"]

    def test_process_error_captured(
        self,
        mock_gemini_client,  # noqa: F811
        temp_image_files: list[Path],
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test that processing errors are captured."""
        mock_gemini_client(generate_error=Exception("API error"))

        group = {
            "original_id": "ORG001",
            "image_paths": temp_image_files[:1],
            "drawing_ids": ["D1"],
            "page_count": 1,
        }

        from common.gemini import GeminiClient

        client = GeminiClient(model_name="gemini-2.0-flash")

        result = _process_single_group(
            group=group,
            system_instruction="Analyze",
            response_schema=sample_response_schema,
            model_name="gemini-2.0-flash",
            client=client,
        )

        assert result["status"] == "image_analysis_error"
        assert "API error" in result["error_detail"]
