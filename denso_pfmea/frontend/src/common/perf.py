"""Performance timing utilities for UI instrumentation."""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class PerformanceEvent:
    """Captured timing information for a logical processing block."""

    name: str
    start: float
    end: float
    metadata: Mapping[str, Any] = field(default_factory=dict)
    order: int = 0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def as_dict(self, origin: float | None = None) -> dict[str, Any]:
        reference = origin if origin is not None else self.start
        return {
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "offset": self.start - reference,
            "metadata": dict(self.metadata or {}),
            "order": self.order,
        }


class PerformanceTracker:
    """Thread-safe collector for performance events."""

    def __init__(self) -> None:
        self._events: list[PerformanceEvent] = []
        self._lock = threading.Lock()
        self._sink: Callable[[PerformanceEvent], None] | None = None
        self._origin: float | None = None
        self._order = 0

    @property
    def origin(self) -> float | None:
        return self._origin

    def start(self, origin: float | None = None) -> None:
        with self._lock:
            self._events.clear()
            self._origin = origin
            self._order = 0

    def set_sink(self, sink: Callable[[PerformanceEvent], None]) -> None:
        with self._lock:
            self._sink = sink
            if not self._events:
                return
            for event in self._events:
                sink(event)
            self._events.clear()

    def record(
        self,
        name: str,
        *,
        start: float | None = None,
        end: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PerformanceEvent:
        begin = start if start is not None else perf_counter()
        finish = end if end is not None else perf_counter()
        meta: Mapping[str, Any] = metadata or {}
        with self._lock:
            if self._origin is None:
                self._origin = begin
            event = PerformanceEvent(
                name=name, start=begin, end=finish, metadata=meta, order=self._order
            )
            self._order += 1
            if self._sink is not None:
                self._sink(event)
            else:
                self._events.append(event)
            return event

    def iter_events(self) -> Iterable[PerformanceEvent]:
        with self._lock:
            snapshot = list(self._events)
        return snapshot


_GLOBAL_TRACKER = PerformanceTracker()


def get_performance_tracker() -> PerformanceTracker:
    return _GLOBAL_TRACKER


@contextmanager
def time_block(
    name: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    tracker: PerformanceTracker | None = None,
) -> Generator[None, None, None]:
    active_tracker = tracker or get_performance_tracker()
    start = perf_counter()
    try:
        yield
    finally:
        active_tracker.record(name, start=start, end=perf_counter(), metadata=metadata)


def record_event(
    name: str,
    *,
    start: float | None = None,
    end: float | None = None,
    metadata: Mapping[str, Any] | None = None,
    tracker: PerformanceTracker | None = None,
) -> PerformanceEvent:
    active_tracker = tracker or get_performance_tracker()
    return active_tracker.record(name, start=start, end=end, metadata=metadata)


__all__ = [
    "PerformanceEvent",
    "PerformanceTracker",
    "get_performance_tracker",
    "record_event",
    "time_block",
]
