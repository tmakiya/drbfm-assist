"""Text chunking utilities for ingestion pipelines (Polars)."""

from typing import Any

import polars as pl
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger


def explode_rows_by_text_chunks(
    df: pl.DataFrame,
    source_field: str,
    chunk_size,
    chunk_overlap,
) -> pl.DataFrame:
    """Split text fields into chunks and expand rows.

    Uses embedding_generation.source_field and optional chunking settings.
    """
    chunk_id_field = "chunk_id"
    total_chunks_field = "total_chunks"

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )

    rows: list[dict[str, Any]] = []
    for row in df.iter_rows(named=True):
        raw_text = row.get(source_field, "")
        if not isinstance(raw_text, str):
            raw_text = ""
        key = raw_text.strip()

        if key:
            chunks = splitter.split_text(key)
            if not chunks:
                chunks = [key]
        else:
            chunks = [""]

        total_chunks = len(chunks) if chunks else 1
        if not chunks:
            chunks = [""]

        for idx, chunk in enumerate(chunks):
            new_row = dict(row)
            new_row[source_field] = chunk
            new_row[chunk_id_field] = idx
            new_row[total_chunks_field] = total_chunks
            rows.append(new_row)

    chunked_df = pl.DataFrame(rows)
    logger.info(
        f"Chunking: chunk_size={chunk_size}, "
        f"chunk_overlap={chunk_overlap}, "
        f"{len(df)} rows -> {len(chunked_df)} chunks"
    )
    return chunked_df
