"""Doc ID utilities for ingestion pipelines."""

import hashlib
from typing import Any

import polars as pl
from loguru import logger


def hash_string_to_int64(text: str) -> int:
    """Hash a string to a 64-bit signed integer."""
    hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:8], byteorder="big", signed=True)


def add_doc_id_from_fields(
    df: pl.DataFrame,
    source_fields: list[str],
    output_field: str = "doc_id",
    separator: str = "_",
) -> pl.DataFrame:
    """Add a deterministic doc_id column based on source fields."""
    if not source_fields:
        raise ValueError("source_fields must not be empty")
    missing = [field for field in source_fields if field not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for doc_id: {', '.join(missing)}")

    def build_key(values: dict[str, Any]) -> str:
        return separator.join(str(values[field]) for field in source_fields)

    result = df.with_columns(
        pl.struct(source_fields)
        .map_elements(lambda values: hash_string_to_int64(build_key(values)), return_dtype=pl.Int64)
        .alias(output_field)
    )
    logger.info(f"Generated {output_field} for {len(result)} records")
    return result
