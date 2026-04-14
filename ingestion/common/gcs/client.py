"""GCS client for downloading files."""

import concurrent.futures
from pathlib import Path

import polars as pl
from google.cloud import storage
from loguru import logger


def _create_client() -> storage.Client:
    """Create a GCS client."""
    return storage.Client()


def download_blob(
    bucket_name: str,
    blob_path: str,
    local_path: Path,
    skip_if_exists: bool = True,
    client: storage.Client | None = None,
) -> bool:
    """Download a single blob from GCS."""
    local_path.parent.mkdir(parents=True, exist_ok=True)

    if skip_if_exists and local_path.exists():
        return True

    try:
        client = client or _create_client()
        blob = client.bucket(bucket_name).blob(blob_path)

        if not blob.exists():
            logger.warning(f"Blob not found: gs://{bucket_name}/{blob_path}")
            return False

        blob.download_to_filename(str(local_path))
        logger.info(f"Downloaded: {local_path.name}")
        return True

    except Exception as e:
        logger.error(f"Download failed {blob_path}: {e}")
        return False


def download_files(
    bucket_name: str,
    blob_paths: list[str],
    local_paths: list[Path],
    max_workers: int = 4,
    skip_if_exists: bool = True,
) -> tuple[int, int]:
    """Download multiple files from GCS in parallel."""
    if len(blob_paths) != len(local_paths):
        raise ValueError("blob_paths and local_paths must have same length")

    if not blob_paths:
        return 0, 0

    client = _create_client()

    def _download(blob_path: str, local_path: Path) -> bool:
        return download_blob(bucket_name, blob_path, local_path, skip_if_exists, client)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_download, blob_paths, local_paths))

    success_count = sum(results)
    return success_count, len(blob_paths)


def _extract_paths(gcs_path: str | None, data_dir: Path) -> tuple[str | None, Path | None]:
    """Extract blob path and local path from GCS URI."""
    if not gcs_path or gcs_path != gcs_path:  # Check for None or NaN
        return None, None

    cleaned = gcs_path.replace("gs://", "")
    if "/" not in cleaned:
        return None, None

    blob_path = cleaned.split("/", 1)[1]
    filename = blob_path.split("/")[-1]
    return blob_path, data_dir / filename


def download_from_dataframe(
    df: pl.DataFrame,
    gcs_path_column: str,
    data_dir: Path,
    bucket_name: str,
    max_workers: int = 4,
) -> pl.DataFrame:
    """Extract GCS paths from DataFrame and download files."""
    data_dir.mkdir(parents=True, exist_ok=True)

    # Extract blob_path and local_path from GCS paths
    gcs_paths = df[gcs_path_column].to_list()
    extracted = [_extract_paths(p, data_dir) for p in gcs_paths]
    blob_paths = [e[0] for e in extracted]
    local_paths = [e[1] for e in extracted]

    # Store local_path as string for Polars compatibility
    local_path_strs = [str(p) if p else None for p in local_paths]

    df = df.with_columns(
        [
            pl.Series("blob_path", blob_paths),
            pl.Series("local_path", local_path_strs),
        ]
    )

    # Filter out rows with no blob_path
    df = df.filter(pl.col("blob_path").is_not_null())

    if df.is_empty():
        return df

    # Convert back to Path for download
    local_path_objs = [Path(p) for p in df["local_path"].to_list()]
    download_files(
        bucket_name,
        df["blob_path"].to_list(),
        local_path_objs,
        max_workers=max_workers,
    )

    # Filter to only rows where local_path exists
    exists_mask = [Path(p).exists() for p in df["local_path"].to_list()]
    return df.filter(pl.Series(exists_mask))
