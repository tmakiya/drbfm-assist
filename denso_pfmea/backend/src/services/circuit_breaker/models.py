"""Circuit Breaker models and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BreakerState(Enum):
    """Circuit Breaker states."""

    CLOSED = "closed"  # Normal: requests pass through
    OPEN = "open"  # Tripped: requests rejected
    HALF_OPEN = "half_open"  # Recovery: testing if service is back


@dataclass(frozen=True)
class BreakerConfig:
    """Circuit Breaker configuration parameters."""

    # Failure rate threshold to trip the breaker (0.0-1.0)
    failure_rate_threshold: float = 0.5  # 50%

    # Window size for calculating failure rate
    window_size: int = 20

    # Duration to stay in OPEN state before transitioning to HALF_OPEN
    open_timeout_seconds: float = 30.0

    # Maximum test calls allowed in HALF_OPEN state
    half_open_max_calls: int = 3

    # Success rate required in HALF_OPEN to transition to CLOSED
    half_open_success_threshold: float = 0.8  # 80%

    def __post_init__(self) -> None:
        if not 0.0 <= self.failure_rate_threshold <= 1.0:
            raise ValueError("failure_rate_threshold must be between 0.0 and 1.0")
        if self.window_size < 1:
            raise ValueError("window_size must be at least 1")
        if self.open_timeout_seconds < 0:
            raise ValueError("open_timeout_seconds must be non-negative")


@dataclass
class BreakerMetrics:
    """Runtime metrics for Circuit Breaker."""

    state: BreakerState
    failure_count: int = 0
    success_count: int = 0
    total_requests: int = 0
    timestamp_state_changed: float = 0.0
    half_open_calls_attempted: int = 0
    failure_rate: float = 0.0
    last_failure_message: str = ""
    time_until_half_open_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class CircuitBreakerError(RuntimeError):
    """Raised when Circuit Breaker rejects a request."""

    pass


class CircuitOpenError(CircuitBreakerError):
    """Raised when Circuit Breaker is in OPEN state."""

    def __init__(self, time_until_half_open: float) -> None:
        self.time_until_half_open = time_until_half_open
        super().__init__(
            f"Circuit Breaker is OPEN. "
            f"Will transition to HALF_OPEN in {time_until_half_open:.1f}s"
        )


__all__ = [
    "BreakerState",
    "BreakerConfig",
    "BreakerMetrics",
    "CircuitBreakerError",
    "CircuitOpenError",
]
