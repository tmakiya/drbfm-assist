"""Thread-based parallel helpers with deterministic ordering and rich errors."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import suppress
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


class ParallelExecutionError(RuntimeError):
    """Parallel実行中に発生した例外をラップし、失敗した要素の情報を持たせる。"""

    def __init__(self, index: int, item: T, message: str):
        super().__init__(message)
        self.index = index
        self.item = item


def _resolve_max_workers(requested: int | None, task_count: int) -> int:
    if task_count <= 0:
        return 1
    if requested is None:
        from os import cpu_count

        cpu = cpu_count() or 1
        return max(1, min(cpu, task_count))
    return max(1, min(requested, task_count))


def get_streamlit_task_wrapper() -> (
    Callable[[Callable[[T], R]], Callable[[T], R]] | None
):
    try:
        from streamlit.runtime.scriptrunner import (
            add_script_run_ctx,
            get_script_run_ctx,
        )
    except (ImportError, RuntimeError):
        return None

    try:
        ctx = get_script_run_ctx(suppress_warning=True)
    except TypeError:  # older signatures
        ctx = get_script_run_ctx()
    if ctx is None:
        return None

    def _wrapper(func: Callable[[T], R]) -> Callable[[T], R]:
        def _run(item: T) -> R:
            thread = threading.current_thread()
            try:
                add_script_run_ctx(thread=thread, ctx=ctx)
            except TypeError:
                add_script_run_ctx(ctx)  # type: ignore[arg-type]
            except RuntimeError:
                pass
            return func(item)

        return _run

    return _wrapper


def parallel_map(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    max_workers: int | None = None,
    task_wrapper: Callable[[Callable[[T], R]], Callable[[T], R]] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[R]:
    """IterablesをThreadPoolで処理し、入力順を維持して結果を返す."""
    data: Sequence[T] = list(items)
    if not data:
        return []

    total = len(data)
    worker_count = _resolve_max_workers(max_workers, total)
    results: list[R | None] = [None] * len(data)
    effective_wrapper = task_wrapper or get_streamlit_task_wrapper()
    wrapped_func = effective_wrapper(func) if effective_wrapper is not None else func

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map: dict[Future[R], tuple[int, T]] = {}
        for index, item in enumerate(data):
            future = executor.submit(wrapped_func, item)
            future_map[future] = (index, item)

        for completed, future in enumerate(as_completed(future_map), start=1):
            index, item = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - re-raised below
                raise ParallelExecutionError(
                    index, item, f"並列タスクが失敗しました: {exc}"
                ) from exc
            results[index] = result
            if progress_callback is not None:
                with suppress(
                    Exception
                ):  # pragma: no cover - 進捗コールバックは握り潰す
                    progress_callback(completed, total)

    # type ignore safe because we fill all entries or raise earlier
    return list(results)  # type: ignore[arg-type]


__all__ = ["parallel_map", "ParallelExecutionError", "get_streamlit_task_wrapper"]
