"""Parallel execution helpers for Gemini analysis tasks."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, TypeVar

import psutil
from loguru import logger

T = TypeVar("T")
R = TypeVar("R")


def run_parallel(
    work_items: list[T],
    worker: Callable[[T], R],
    *,
    max_workers: int,
    log_label: str = "Progress",
    log_every: int = 10,
    item_label: str = "items",
    on_error: Callable[[T, Exception], R] | None = None,
) -> tuple[list[R | None], list[dict[str, Any]]]:
    """Run worker over work_items in parallel and collect results.

    Returns results in input order and a list of error details.
    """
    if not work_items:
        return [], []

    total = len(work_items)
    workers = max(1, max_workers)
    results: list[R | None] = [None] * total
    errors: list[dict[str, Any]] = []
    process = psutil.Process()
    initial_memory_mb = process.memory_info().rss / 1024 / 1024
    success_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {executor.submit(worker, item): idx for idx, item in enumerate(work_items)}
        completed = 0
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                results[idx] = future.result()
                success_count += 1
            except Exception as exc:
                message = str(exc.__cause__) if exc.__cause__ else str(exc)
                errors.append({"index": idx, "message": message})
                if on_error is not None:
                    try:
                        results[idx] = on_error(work_items[idx], exc)
                    except Exception:
                        results[idx] = None

            completed += 1
            if log_every > 0 and (completed % log_every == 0 or completed == total):
                percentage = completed * 100 // total
                current_memory_mb = process.memory_info().rss / 1024 / 1024
                memory_delta_mb = current_memory_mb - initial_memory_mb
                logger.info(
                    f"{log_label}: [{percentage:3d}%] {completed}/{total} {item_label} "
                    f"({success_count} successful) | Memory: {current_memory_mb:.1f} MB "
                    f"(+{memory_delta_mb:.1f} MB)"
                )

    return results, errors
