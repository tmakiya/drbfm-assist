"""
GCSから画像をダウンロードするスクリプト

Usage:
    python scripts/preprocess/download_images_from_csv.py <csv_file> <output_dir>

Example:
    python scripts/preprocess/download_images_from_csv.py \
        data/purpose/purpose_品質会議提議内容詳細_drawing_ids.csv \
        data/purpose/images
"""

import concurrent.futures
import sys
from pathlib import Path

import pandas as pd
from google.cloud import storage
from loguru import logger


def download_blob(bucket: storage.Bucket, source_blob_name: str, destination_file_name: Path) -> bool:
    """Download a blob from the bucket.
    
    Args:
        bucket: GCS bucket object
        source_blob_name: Path to the blob in GCS (without gs://bucket_name/ prefix)
        destination_file_name: Local path to save the file
        
    Returns:
        True if download was successful, False otherwise
    """
    destination_file_name.parent.mkdir(parents=True, exist_ok=True)
    if destination_file_name.exists():
        logger.debug(f"File already exists: {destination_file_name}")
        return True

    blob = bucket.blob(source_blob_name)
    if not blob.exists():
        logger.warning(f"Blob does not exist in GCS: {source_blob_name}")
        return False

    blob.download_to_filename(destination_file_name)
    return True


def parse_gcs_path(gcs_path: str) -> tuple[str, str]:
    """Parse GCS path into bucket name and blob path.
    
    Args:
        gcs_path: Full GCS path (e.g., gs://bucket_name/path/to/file.png)
        
    Returns:
        Tuple of (bucket_name, blob_path)
    """
    if not gcs_path.startswith("gs://"):
        raise ValueError(f"Invalid GCS path: {gcs_path}")
    
    # Remove gs:// prefix
    path_without_prefix = gcs_path[5:]
    # Split into bucket name and blob path
    parts = path_without_prefix.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS path: {gcs_path}")
    
    return parts[0], parts[1]


def download_images_from_csv(
    csv_path: Path,
    output_dir: Path,
    n_worker: int = 4,
) -> None:
    """Download images from GCS based on CSV file.
    
    Args:
        csv_path: Path to CSV file containing drawing_id and drawing_img_path columns
        output_dir: Directory to save downloaded images
        n_worker: Number of parallel download workers
    """
    logger.info(f"Reading CSV file: {csv_path}")
    df = pd.read_csv(csv_path)
    
    required_columns = ["drawing_id", "drawing_img_path"]
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    
    logger.info(f"Found {len(df)} records in CSV")
    
    # Group by bucket name for efficient downloading
    storage_client = storage.Client()
    buckets: dict[str, storage.Bucket] = {}
    
    download_tasks = []
    for _, row in df.iterrows():
        drawing_id = row["drawing_id"]
        gcs_path = row["drawing_img_path"]
        
        try:
            bucket_name, blob_path = parse_gcs_path(gcs_path)
        except ValueError as e:
            logger.warning(f"Skipping invalid GCS path: {e}")
            continue
        
        if bucket_name not in buckets:
            buckets[bucket_name] = storage_client.bucket(bucket_name)
        
        local_path = output_dir / f"{drawing_id}.png"
        download_tasks.append((buckets[bucket_name], blob_path, local_path))
    
    logger.info(f"Starting download of {len(download_tasks)} files from GCS")
    
    success_count = 0
    fail_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_worker) as executor:
        futures = {
            executor.submit(download_blob, bucket, blob_path, local_path): (blob_path, local_path)
            for bucket, blob_path, local_path in download_tasks
        }
        
        for idx, future in enumerate(concurrent.futures.as_completed(futures)):
            blob_path, local_path = futures[future]
            try:
                result = future.result()
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"Error downloading {blob_path}: {e}")
                fail_count += 1
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Progress: {idx + 1:,} / {len(download_tasks):,} images processed")
    
    logger.info(f"Download completed: {success_count} succeeded, {fail_count} failed")


def main():
    if len(sys.argv) != 3:
        print("Usage: python download_images_from_csv.py <csv_file> <output_dir>")
        print("Example: python download_images_from_csv.py data/purpose/purpose_品質会議提議内容詳細_drawing_ids.csv data/purpose/images")
        sys.exit(1)
    
    csv_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    download_images_from_csv(csv_path, output_dir)


if __name__ == "__main__":
    main()
