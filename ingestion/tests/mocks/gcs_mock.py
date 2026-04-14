"""Mock classes for GCS client testing."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class MockBlob:
    """Mock GCS Blob."""

    def __init__(
        self,
        name: str,
        exists: bool = True,
        content: bytes = b"mock content",
    ):
        self.name = name
        self._exists = exists
        self._content = content

    def exists(self) -> bool:
        """Check if blob exists."""
        return self._exists

    def download_to_filename(self, filename: str) -> None:
        """Download blob content to a local file."""
        if not self._exists:
            raise Exception(f"Blob {self.name} does not exist")
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(self._content)


class MockBucket:
    """Mock GCS Bucket."""

    def __init__(
        self,
        name: str,
        blobs: dict[str, MockBlob] | None = None,
    ):
        self.name = name
        self._blobs = blobs or {}

    def blob(self, blob_name: str) -> MockBlob:
        """Get a blob by name."""
        if blob_name in self._blobs:
            return self._blobs[blob_name]
        # Return a non-existent blob by default
        return MockBlob(blob_name, exists=False)

    def add_blob(
        self,
        blob_name: str,
        content: bytes = b"mock content",
    ) -> MockBlob:
        """Add a blob to the bucket."""
        blob = MockBlob(blob_name, exists=True, content=content)
        self._blobs[blob_name] = blob
        return blob


class MockGCSClient:
    """Mock GCS Client."""

    def __init__(self, buckets: dict[str, MockBucket] | None = None):
        self._buckets = buckets or {}

    def bucket(self, bucket_name: str) -> MockBucket:
        """Get a bucket by name."""
        if bucket_name in self._buckets:
            return self._buckets[bucket_name]
        # Create an empty bucket if it doesn't exist
        bucket = MockBucket(bucket_name)
        self._buckets[bucket_name] = bucket
        return bucket

    def add_bucket(self, bucket_name: str) -> MockBucket:
        """Add a bucket."""
        bucket = MockBucket(bucket_name)
        self._buckets[bucket_name] = bucket
        return bucket


@pytest.fixture
def mock_gcs_client(monkeypatch: pytest.MonkeyPatch):
    """Fixture to mock GCS client.

    Returns a factory function to create configured mocks.

    Example:
        def test_download(mock_gcs_client):
            client = mock_gcs_client(
                bucket_name="my-bucket",
                blob_configs={"path/to/file.png": b"file content"}
            )

            # Now GCS operations will use the mock

    """

    def _create_mock(
        bucket_name: str = "test-bucket",
        blob_configs: dict[str, bytes] | None = None,
    ) -> MockGCSClient:
        blobs: dict[str, MockBlob] = {}
        if blob_configs:
            for blob_name, content in blob_configs.items():
                blobs[blob_name] = MockBlob(blob_name, exists=True, content=content)

        bucket = MockBucket(bucket_name, blobs)
        client = MockGCSClient({bucket_name: bucket})

        # Mock the Client class
        mock_client_class = MagicMock(return_value=client)
        monkeypatch.setattr("google.cloud.storage.Client", mock_client_class)

        return client

    return _create_mock


@pytest.fixture
def mock_gcs_download_failure(monkeypatch: pytest.MonkeyPatch):
    """Fixture to mock GCS download failure."""
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_to_filename.side_effect = Exception("Download failed")

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    mock_client_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("google.cloud.storage.Client", mock_client_class)

    return mock_client
