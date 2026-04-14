"""Batch processing utilities for ingestion pipelines."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class BatchContext:
    """Batch context values passed to a per-batch processor."""

    batch_num: int
    offset: int
    batch_size: int
    truncate: bool
    dry_run: bool
    total_rows: int
    num_batches: int


class SingleBatchProcessor:
    """Callable wrapper that adapts a per-batch function to the BatchContext API.

    This is a thin dependency-injection helper:
    - Binds static keyword arguments (pipeline_dir, config, etc.).
    - Exposes a single __call__(context) entry point for run_batch_processing.
    - Keeps run_batch_processing generic by avoiding config-specific signatures.
    """

    def __init__(self, func: Callable[..., dict[str, Any]], **kwargs: Any) -> None:
        self._func = func
        self._kwargs = kwargs

    def __call__(self, context: BatchContext) -> dict[str, Any]:
        return self._func(context, **self._kwargs)


def cap_total_rows(total_rows: int) -> int:
    """Cap total rows using QUERY_FILE_LIMIT (default 100000)."""
    limit = int(os.getenv("QUERY_FILE_LIMIT", 100000))
    if total_rows > limit:
        logger.info(f"Capping total rows from {total_rows} to {limit} due to QUERY_FILE_LIMIT")
        return limit
    else:
        return total_rows


def run_batch_processing(
    total_rows: int,
    batch_size: int,
    truncate: bool,
    dry_run: bool,
    batch_fn: Callable[[BatchContext], dict[str, Any]],
    *,
    continue_on_error: bool = True,
) -> dict[str, int]:
    """Run a batch processing loop with shared progress/error handling.

    The batch_fn callable should return a dict with keys: total, success, errors.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    total_rows = cap_total_rows(total_rows)

    num_batches = (total_rows + batch_size - 1) // batch_size if total_rows > 0 else 0
    logger.info(f"Processing {total_rows:,} records in {num_batches} batches of {batch_size}")

    overall_stats = {
        "total": 0,
        "success": 0,
        "errors": 0,
        "batches_completed": 0,
        "batches_failed": 0,
        "batch_size": batch_size,
        "num_batches": num_batches,
    }

    for batch_num in range(1, num_batches + 1):
        offset = (batch_num - 1) * batch_size
        remaining = total_rows - offset
        current_batch_size = min(batch_size, remaining)

        if current_batch_size <= 0:
            logger.warning(f"Batch {batch_num}: No remaining records, stopping")
            break

        batch_truncate = truncate and batch_num == 1
        context = BatchContext(
            batch_num=batch_num,
            offset=offset,
            batch_size=current_batch_size,
            truncate=batch_truncate,
            dry_run=dry_run,
            total_rows=total_rows,
            num_batches=num_batches,
        )

        try:
            result = batch_fn(context)

            overall_stats["total"] += result.get("total", 0)
            overall_stats["success"] += result.get("success", 0)
            overall_stats["errors"] += result.get("errors", 0)
            overall_stats["batches_completed"] += 1

            logger.info(
                f"Overall progress: {overall_stats['batches_completed']}/{num_batches} batches, "
                f"{overall_stats['success']}/{overall_stats['total']} records succeeded"
            )

        except Exception as exc:
            logger.error(f"Batch {batch_num} failed with error: {exc}")
            overall_stats["batches_failed"] += 1
            if not continue_on_error:
                raise
            logger.warning("Continuing to next batch...")

    return overall_stats
