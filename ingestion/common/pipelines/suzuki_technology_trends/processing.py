"""Processing utilities for Suzuki Technology Trends pipeline."""

from __future__ import annotations

from typing import Any

import polars as pl
from loguru import logger

from common.gemini import generate_embeddings_batch

from .config import EmbeddingConfig

LIST_FIELDS = ("components_theme", "issue_theme", "technology_theme")


def add_embeddings(df: pl.DataFrame, embedding_config: EmbeddingConfig) -> pl.DataFrame:
    """Generate embeddings and add to DataFrame.

    Args:
        df: DataFrame with source text
        embedding_config: Embedding configuration

    Returns:
        DataFrame with embeddings added and empty embeddings filtered out

    Raises:
        ValueError: If no valid embeddings are generated

    """
    logger.info("Generating embeddings...")

    # Extract texts from the source field
    texts = df[embedding_config.source_field].to_list()

    # Generate embeddings using Gemini with parallel processing
    logger.info(f"Processing {len(texts)} texts with parallel embedding generation...")
    embeddings, embedding_summary = generate_embeddings_batch(
        texts=texts,
        model_name=embedding_config.model,
        task_type=embedding_config.task_type,
        dimensionality=embedding_config.dimensionality,
        normalize=embedding_config.normalize,
        max_workers=embedding_config.max_workers,
    )

    # Convert empty lists to None (for empty source field)
    embeddings_processed = [emb if emb and len(emb) > 0 else None for emb in embeddings]
    df = df.with_columns(pl.Series("embedding", embeddings_processed))

    logger.info(f"Generated {embedding_summary.get('embedded', 0)}/{len(embeddings_processed)} embeddings")

    return df


def _split_field(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.split(",")
    else:
        return []
    cleaned = []
    for item in items:
        item_str = str(item).strip()
        if item_str:
            cleaned.append(item_str)
    return cleaned


def split_theme_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Split comma-separated theme columns into lists."""
    LIST_FIELDS = ("components_theme", "issue_theme", "technology_theme")
    columns = [
        pl.col(field).map_elements(_split_field, return_dtype=pl.List(pl.Utf8)).alias(field)
        for field in LIST_FIELDS
        if field in df.columns
    ]
    return df if not columns else df.with_columns(columns)
