"""Sample data fixtures for testing.

This module provides factory functions for creating test data.
"""

from typing import Any

import polars as pl


def create_drawing_df(
    num_drawings: int = 3,
    num_originals: int = 2,
    local_paths: list[str] | None = None,
) -> pl.DataFrame:
    """Create a sample drawing DataFrame.

    Args:
        num_drawings: Number of drawing records to create.
        num_originals: Number of distinct original_ids.
        local_paths: Optional list of local file paths.

    Returns:
        DataFrame with drawing data.

    """
    drawing_ids = [f"DRW{i:03d}" for i in range(1, num_drawings + 1)]
    original_ids = [f"ORG{(i % num_originals) + 1:03d}" for i in range(num_drawings)]

    # Assign page numbers based on original_id
    page_numbers = []
    page_counters: dict[str, int] = {}
    for orig_id in original_ids:
        page_counters[orig_id] = page_counters.get(orig_id, 0) + 1
        page_numbers.append(page_counters[orig_id])

    file_paths = [f"gs://bucket/path/img{i}.png" for i in range(1, num_drawings + 1)]
    blob_paths = [f"path/img{i}.png" for i in range(1, num_drawings + 1)]

    if local_paths is None:
        local_paths = [f"/tmp/img{i}.png" for i in range(1, num_drawings + 1)]

    return pl.DataFrame(
        {
            "drawing_id": drawing_ids,
            "original_id": original_ids,
            "page_number": page_numbers,
            "file_path": file_paths,
            "blob_path": blob_paths,
            "local_path": local_paths,
        }
    )


def create_analysis_result(
    original_id: str = "ORG001",
    drawing_ids: list[str] | None = None,
    status: str = "success",
    error_detail: str = "",
    page_count: int = 1,
    total_size: int = 1024,
    **extra_fields: Any,
) -> dict[str, Any]:
    """Create a sample analysis result.

    Args:
        original_id: The original document ID.
        drawing_ids: List of drawing IDs in the group.
        status: Status of the analysis (success, skipped_large_file, etc).
        error_detail: Error message if failed.
        page_count: Number of pages analyzed.
        total_size: Total size of images in bytes.
        **extra_fields: Additional fields to include.

    Returns:
        Analysis result dictionary.

    """
    if drawing_ids is None:
        drawing_ids = [f"DRW_{original_id}"]

    result = {
        "original_id": original_id,
        "drawing_ids": drawing_ids,
        "page_count": page_count,
        "total_size": total_size,
        "status": status,
        "error_detail": error_detail,
        # Default analysis fields
        "cause_original": "",
        "cause_unit": "",
        "cause_part": [],
        "unit_part_change": "",
        "failure_mode": "",
        "failure_effect": "",
        "countermeasures": "",
    }

    if status == "success":
        result.update(
            {
                "cause_original": f"原因事象_{original_id}",
                "cause_unit": "テストユニット1",
                "cause_part": ["部品A"],
                "unit_part_change": f"変更内容_{original_id}",
                "failure_mode": "摩耗",
                "failure_effect": "動作不良",
                "countermeasures": f"対策_{original_id}",
            }
        )

    result.update(extra_fields)
    return result


def create_embedding(dimensionality: int = 768, seed: float = 0.1) -> list[float]:
    """Create a sample embedding vector.

    Args:
        dimensionality: Size of the embedding vector.
        seed: Base value for generating embeddings.

    Returns:
        List of float values representing an embedding.

    """
    return [seed + (i * 0.0001) for i in range(dimensionality)]


def create_isp_config() -> dict[str, Any]:
    """Create a sample ISP configuration.

    Returns:
        ISP configuration dictionary.

    """
    return {
        "isp": {
            "index_name": "test-defects",
            "id_field": "doc_id",
            "fields": {
                "doc_id": "doc_id",
                "original_id": "original_id",
                "cause": {
                    "original": "cause_original",
                    "unit": "cause_unit",
                    "part": "cause_part",
                    "part_change": "unit_part_change",
                },
                "failure": {
                    "mode": "failure_mode",
                    "effect": "failure_effect",
                },
                "countermeasures": "countermeasures",
            },
            "mappings": {
                "properties": {
                    "doc_id": {"type": "long"},
                    "original_id": {"type": "keyword"},
                    "cause_unit": {"type": "text"},
                    "embedding": {"type": "dense_vector", "dims": 768},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
        }
    }
