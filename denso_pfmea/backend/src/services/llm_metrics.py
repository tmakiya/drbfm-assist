from __future__ import annotations

import json
import logging
import math
import os
import threading
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)

_PERCENTILE_WINDOW = 200


def metrics_enabled() -> bool:
    value = os.environ.get("SOL_PFMEA_METRICS_ENABLED")
    if value is None:
        return True
    lowered = value.lower()
    return lowered not in {"0", "false", "off"}


@dataclass
class OperationStats:
    total_calls: int = 0
    success_calls: int = 0
    error_calls: int = 0
    total_duration: float = 0.0
    durations: deque[float] = field(
        default_factory=lambda: deque(maxlen=_PERCENTILE_WINDOW)
    )
    rate_limit_hits: int = 0
    malformed_responses: int = 0
    metadata_samples: deque[Mapping[str, Any]] = field(
        default_factory=lambda: deque(maxlen=5)
    )

    def record(self, status: str, duration: float, metadata: Mapping[str, Any]) -> None:
        self.total_calls += 1
        if status == "success":
            self.success_calls += 1
        else:
            self.error_calls += 1
        self.total_duration += duration
        self.durations.append(duration)
        if metadata:
            self.metadata_samples.append(dict(metadata))

    def average_latency(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration / self.total_calls

    def percentile(self, percentile: float) -> float:
        if not self.durations:
            return 0.0
        sorted_samples = sorted(self.durations)
        k = (len(sorted_samples) - 1) * percentile
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_samples[int(k)]
        return sorted_samples[int(f)] * (c - k) + sorted_samples[int(c)] * (k - f)

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "error_calls": self.error_calls,
            "rate_limit_hits": self.rate_limit_hits,
            "malformed_responses": self.malformed_responses,
            "avg_latency_ms": round(self.average_latency() * 1000, 2),
            "p95_latency_ms": round(self.percentile(0.95) * 1000, 2),
            "recent_metadata": list(self.metadata_samples),
        }


class LLMMetricsAggregator:
    """Thread-safe aggregator for LLM execution metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._operations: dict[str, OperationStats] = {}
        self._last_error: dict[str, Any] = {}
        self._last_call: dict[str, Any] = {}

    def reset(self) -> None:
        if not metrics_enabled():
            return
        with self._lock:
            self._operations.clear()
            self._last_error = {}
            self._last_call = {}

    def _get_stats(self, operation: str) -> OperationStats:
        stats = self._operations.get(operation)
        if stats is None:
            stats = OperationStats()
            self._operations[operation] = stats
        return stats

    def record_call(
        self,
        operation: str,
        status: str,
        *,
        duration: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not metrics_enabled():
            return
        meta = dict(metadata or {})
        with self._lock:
            stats = self._get_stats(operation)
            stats.record(status, duration, meta)
            self._last_call = {
                "operation": operation,
                "status": status,
                "duration": duration,
                "metadata": meta,
            }
            if status != "success":
                self._last_error = dict(self._last_call)

    def record_rate_limit(self, operation: str, *, attempt: int, message: str) -> None:
        if not metrics_enabled():
            return
        with self._lock:
            stats = self._get_stats(operation)
            stats.rate_limit_hits += 1
        logger.warning(
            "LLM rate limit detected (operation=%s, attempt=%d): %s",
            operation,
            attempt,
            message,
        )

    def record_malformed_response(
        self, operation: str, *, attempt: int, message: str
    ) -> None:
        if not metrics_enabled():
            return
        with self._lock:
            stats = self._get_stats(operation)
            stats.malformed_responses += 1
            self._last_error = {
                "operation": operation,
                "status": "malformed_response",
                "metadata": {"message": message, "attempt": attempt},
            }
        logger.warning(
            "LLM malformed response detected (operation=%s, attempt=%d): %s",
            operation,
            attempt,
            message,
        )

    def snapshot(self) -> dict[str, Any]:
        if not metrics_enabled():
            return {}
        with self._lock:
            operations = {
                name: stats.snapshot() for name, stats in self._operations.items()
            }
            totals = self._aggregate_totals(self._operations.values())
            return {
                "enabled": metrics_enabled(),
                "operations": operations,
                "totals": totals,
                "last_call": dict(self._last_call),
                "last_error": dict(self._last_error),
            }

    @staticmethod
    def _aggregate_totals(stats: Iterable[OperationStats]) -> dict[str, Any]:
        total_calls = sum(item.total_calls for item in stats)
        success_calls = sum(item.success_calls for item in stats)
        error_calls = sum(item.error_calls for item in stats)
        rate_limit_hits = sum(item.rate_limit_hits for item in stats)
        malformed_responses = sum(item.malformed_responses for item in stats)
        durations = [duration for item in stats for duration in item.durations]
        avg_latency = mean(durations) if durations else 0.0
        sorted_samples = sorted(durations)
        p95_latency = 0.0
        if sorted_samples:
            k = (len(sorted_samples) - 1) * 0.95
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                p95_latency = sorted_samples[int(k)]
            else:
                p95_latency = sorted_samples[int(f)] * (c - k) + sorted_samples[
                    int(c)
                ] * (k - f)
        return {
            "total_calls": total_calls,
            "success_calls": success_calls,
            "error_calls": error_calls,
            "rate_limit_hits": rate_limit_hits,
            "malformed_responses": malformed_responses,
            "avg_latency_ms": round(avg_latency * 1000, 2),
            "p95_latency_ms": round(p95_latency * 1000, 2),
        }


_GLOBAL_AGGREGATOR = LLMMetricsAggregator()


def get_llm_metrics() -> LLMMetricsAggregator:
    return _GLOBAL_AGGREGATOR


def persist_metrics_summary(
    output_path: str | None = None,
    *,
    include_operations: bool = True,
) -> str:
    """Persist current metrics snapshot to a JSON file.

    Args:
        output_path: Path to output file. If None, uses runtime/logs/llm_metrics_summary.json
        include_operations: Whether to include per-operation breakdown (default: True)

    Returns:
        Path to the persisted file
    """
    if not metrics_enabled():
        logger.warning("Metrics are disabled. No summary will be persisted.")
        return ""

    if output_path is None:
        # Use default path in runtime/logs
        output_path = "runtime/logs/llm_metrics_summary.json"

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    snapshot = _GLOBAL_AGGREGATOR.snapshot()

    # Add metadata
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics_enabled": snapshot.get("enabled", True),
        "totals": snapshot.get("totals", {}),
    }

    if include_operations:
        summary["operations"] = snapshot.get("operations", {})

    summary["last_call"] = snapshot.get("last_call", {})
    summary["last_error"] = snapshot.get("last_error", {})

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info(
        "LLM metrics summary persisted to %s (total_calls=%d)",
        output_path,
        summary["totals"].get("total_calls", 0),
    )

    return str(output_file)


def load_metrics_summary(
    input_path: str = "runtime/logs/llm_metrics_summary.json",
) -> dict[str, Any]:
    """Load metrics summary from a JSON file.

    Args:
        input_path: Path to metrics summary file

    Returns:
        Dictionary containing metrics summary

    Raises:
        FileNotFoundError: If the file does not exist
        json.JSONDecodeError: If the file is not valid JSON
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Metrics summary file not found: {input_path}")

    with input_file.open("r", encoding="utf-8") as f:
        result = json.load(f)
        return dict(result) if isinstance(result, dict) else {}


__all__ = [
    "LLMMetricsAggregator",
    "get_llm_metrics",
    "metrics_enabled",
    "persist_metrics_summary",
    "load_metrics_summary",
]
