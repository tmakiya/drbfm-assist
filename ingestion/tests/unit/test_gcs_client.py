"""Unit tests for GCS client."""

from pathlib import Path

import polars as pl
import pytest
from common.gcs.client import (
    _extract_paths,
    download_blob,
    download_files,
    download_from_dataframe,
)

# Import mock fixtures


class TestDownloadBlob:
    """Tests for download_blob function."""

    def test_download_success(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test successful blob download."""
        content = b"test file content"
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={"path/to/file.png": content},
        )

        local_path = tmp_path / "downloaded.png"
        result = download_blob(
            bucket_name="test-bucket",
            blob_path="path/to/file.png",
            local_path=local_path,
        )

        assert result is True
        assert local_path.exists()
        assert local_path.read_bytes() == content

    def test_download_blob_not_found(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test download when blob doesn't exist."""
        mock_gcs_client(bucket_name="test-bucket", blob_configs={})

        local_path = tmp_path / "missing.png"
        result = download_blob(
            bucket_name="test-bucket",
            blob_path="nonexistent/file.png",
            local_path=local_path,
        )

        assert result is False
        assert not local_path.exists()

    def test_download_skip_if_exists(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that download is skipped if file exists."""
        mock_gcs_client(bucket_name="test-bucket")

        local_path = tmp_path / "existing.png"
        local_path.write_bytes(b"existing content")

        result = download_blob(
            bucket_name="test-bucket",
            blob_path="path/to/file.png",
            local_path=local_path,
            skip_if_exists=True,
        )

        assert result is True
        # Content should not have changed
        assert local_path.read_bytes() == b"existing content"

    def test_download_overwrite_if_skip_disabled(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that file is overwritten when skip_if_exists is False."""
        new_content = b"new content"
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={"path/to/file.png": new_content},
        )

        local_path = tmp_path / "existing.png"
        local_path.write_bytes(b"old content")

        result = download_blob(
            bucket_name="test-bucket",
            blob_path="path/to/file.png",
            local_path=local_path,
            skip_if_exists=False,
        )

        assert result is True
        assert local_path.read_bytes() == new_content

    def test_download_creates_parent_directories(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that parent directories are created."""
        content = b"content"
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={"file.png": content},
        )

        local_path = tmp_path / "nested" / "deep" / "path" / "file.png"
        result = download_blob(
            bucket_name="test-bucket",
            blob_path="file.png",
            local_path=local_path,
        )

        assert result is True
        assert local_path.exists()

    def test_download_failure_returns_false(
        self,
        mock_gcs_download_failure,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that download failure returns False."""
        local_path = tmp_path / "failed.png"
        result = download_blob(
            bucket_name="test-bucket",
            blob_path="path/to/file.png",
            local_path=local_path,
        )

        assert result is False


class TestDownloadFiles:
    """Tests for download_files function."""

    def test_download_multiple_files(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test downloading multiple files in parallel."""
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={
                "file1.png": b"content1",
                "file2.png": b"content2",
                "file3.png": b"content3",
            },
        )

        blob_paths = ["file1.png", "file2.png", "file3.png"]
        local_paths = [tmp_path / f"local_{i}.png" for i in range(3)]

        success, total = download_files(
            bucket_name="test-bucket",
            blob_paths=blob_paths,
            local_paths=local_paths,
        )

        assert success == 3
        assert total == 3
        for path in local_paths:
            assert path.exists()

    def test_download_empty_list(
        self,
        mock_gcs_client,  # noqa: F811
    ) -> None:
        """Test downloading empty file list."""
        mock_gcs_client(bucket_name="test-bucket")

        success, total = download_files(
            bucket_name="test-bucket",
            blob_paths=[],
            local_paths=[],
        )

        assert success == 0
        assert total == 0

    def test_download_mismatched_lengths_raises(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that mismatched blob/local path lengths raise ValueError."""
        mock_gcs_client(bucket_name="test-bucket")

        with pytest.raises(ValueError, match="must have same length"):
            download_files(
                bucket_name="test-bucket",
                blob_paths=["file1.png", "file2.png"],
                local_paths=[tmp_path / "local1.png"],
            )

    def test_download_partial_success(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test partial download success (some files missing)."""
        # Only one file exists
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={"file1.png": b"content1"},
        )

        blob_paths = ["file1.png", "missing.png", "also_missing.png"]
        local_paths = [tmp_path / f"local_{i}.png" for i in range(3)]

        success, total = download_files(
            bucket_name="test-bucket",
            blob_paths=blob_paths,
            local_paths=local_paths,
        )

        assert success == 1
        assert total == 3


class TestExtractPaths:
    """Tests for _extract_paths helper function."""

    def test_extract_valid_gcs_path(self, tmp_path: Path) -> None:
        """Test extracting paths from valid GCS URI."""
        gcs_path = "gs://my-bucket/path/to/file.png"
        blob_path, local_path = _extract_paths(gcs_path, tmp_path)

        assert blob_path == "path/to/file.png"
        assert local_path == tmp_path / "file.png"

    def test_extract_none_path(self, tmp_path: Path) -> None:
        """Test extracting paths from None."""
        blob_path, local_path = _extract_paths(None, tmp_path)

        assert blob_path is None
        assert local_path is None

    def test_extract_invalid_path_no_slash(self, tmp_path: Path) -> None:
        """Test extracting paths from path without slash."""
        blob_path, local_path = _extract_paths("gs://bucket", tmp_path)

        assert blob_path is None
        assert local_path is None


class TestDownloadFromDataFrame:
    """Tests for download_from_dataframe function."""

    def test_download_from_dataframe_success(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test downloading files listed in DataFrame."""
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={
                "path/img1.png": b"content1",
                "path/img2.png": b"content2",
            },
        )

        df = pl.DataFrame(
            {
                "id": [1, 2],
                "file_path": [
                    "gs://test-bucket/path/img1.png",
                    "gs://test-bucket/path/img2.png",
                ],
            }
        )

        result_df = download_from_dataframe(
            df=df,
            gcs_path_column="file_path",
            data_dir=tmp_path,
            bucket_name="test-bucket",
        )

        assert len(result_df) == 2
        assert "blob_path" in result_df.columns
        assert "local_path" in result_df.columns

    def test_download_from_dataframe_filters_missing(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that missing files are filtered from result."""
        # Only first file exists
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={"path/img1.png": b"content1"},
        )

        df = pl.DataFrame(
            {
                "id": [1, 2],
                "file_path": [
                    "gs://test-bucket/path/img1.png",
                    "gs://test-bucket/path/missing.png",
                ],
            }
        )

        result_df = download_from_dataframe(
            df=df,
            gcs_path_column="file_path",
            data_dir=tmp_path,
            bucket_name="test-bucket",
        )

        # Only successfully downloaded files should remain
        assert len(result_df) == 1
        assert result_df["id"][0] == 1

    def test_download_from_dataframe_creates_data_dir(
        self,
        mock_gcs_client,  # noqa: F811
        tmp_path: Path,
    ) -> None:
        """Test that data directory is created if it doesn't exist."""
        mock_gcs_client(
            bucket_name="test-bucket",
            blob_configs={"path/img.png": b"content"},
        )

        data_dir = tmp_path / "new_dir" / "nested"
        df = pl.DataFrame(
            {
                "file_path": ["gs://test-bucket/path/img.png"],
            }
        )

        download_from_dataframe(
            df=df,
            gcs_path_column="file_path",
            data_dir=data_dir,
            bucket_name="test-bucket",
        )

        assert data_dir.exists()
