"""Document preparation helpers for ISP ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl
from loguru import logger


def build_document_from_mapping(
    row: Mapping[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    """Build a document from a field mapping definition."""
    document: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            document[key] = build_document_from_mapping(
                row,
                value,
            )
        elif isinstance(value, str):
            document[key] = row.get(value)
        else:
            raise ValueError(f"Unsupported mapping for '{key}': {type(value).__name__}")
    return document


def prepare_documents(df: pl.DataFrame, field_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Prepare documents for ISP indexing from a DataFrame."""
    documents = []
    for row in df.iter_rows(named=True):
        document = build_document_from_mapping(row, field_config)
        for field in ("doc_id", "embedding", "chunk_id", "total_chunks"):
            value = row.get(field)
            if value is not None:
                document[field] = value
        documents.append(document)

    logger.info(f"Prepared {len(documents)} documents for ISP")
    return documents
