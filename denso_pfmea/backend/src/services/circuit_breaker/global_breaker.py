"""Global Circuit Breaker for LLM calls."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from .models import (
    BreakerConfig,
    BreakerMetrics,
    BreakerState,
    CircuitOpenError,
)

logger = logging.getLogger(__name__)


class GlobalCircuitBreaker:
    """
    Global Circuit Breaker for all LLM calls.

    Monitors failure rate across all LLM requests and trips when the rate
    exceeds the configured threshold. This prevents thundering herd effects
    when the LLM service is experiencing rate limiting.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit tripped, requests are rejected immediately
    - HALF_OPEN: Testing if service recovered, limited requests allowed

    Usage:
        breaker = GlobalCircuitBreaker()

        # Before making an LLM call
        breaker.check_can_proceed()  # Raises CircuitOpenError if OPEN

        try:
            result = make_llm_call()
            breaker.record_success()
        except RateLimitError:
            breaker.record_failure(is_rate_limit=True)
            raise
    """

    def __init__(self, config: BreakerConfig | None = None) -> None:
        self._config = config or BreakerConfig()
        self._lock = threading.RLock()

        self._state = BreakerState.CLOSED
        self._timestamp_state_changed = time.time()

        # Sliding window of recent request results (True=success, False=failure)
        self._recent_requests: deque[bool] = deque(maxlen=self._config.window_size)

        self._half_open_attempts = 0
        self._last_failure_message = ""

    def get_state(self) -> BreakerState:
        """Get current Circuit Breaker state."""
        with self._lock:
            self._update_state_if_needed()
            return self._state

    def record_success(self) -> None:
        """Record a successful LLM call."""
        with self._lock:
            self._recent_requests.append(True)
            self._update_state_if_needed()

            if self._state == BreakerState.HALF_OPEN:
                self._half_open_attempts += 1
                # Check if we've recovered
                if (
                    self._half_open_success_rate()
                    >= self._config.half_open_success_threshold
                ):
                    self._transition_to(BreakerState.CLOSED)

    def record_failure(self, *, is_rate_limit: bool = False, message: str = "") -> None:
        """Record a failed LLM call."""
        with self._lock:
            self._recent_requests.append(False)
            if message:
                self._last_failure_message = message
            self._update_state_if_needed()

            if self._state == BreakerState.HALF_OPEN and is_rate_limit:
                # Rate limit in HALF_OPEN means service is still struggling
                self._transition_to(BreakerState.OPEN)

    def check_can_proceed(self) -> None:
        """
        Check if a request can proceed.

        Raises:
            CircuitOpenError: If the circuit is OPEN
        """
        with self._lock:
            self._update_state_if_needed()
            if self._state == BreakerState.OPEN:
                raise CircuitOpenError(self._time_until_half_open())

    def get_metrics(self) -> BreakerMetrics:
        """Get current metrics snapshot."""
        with self._lock:
            self._update_state_if_needed()
            return BreakerMetrics(
                state=self._state,
                failure_count=sum(1 for r in self._recent_requests if not r),
                success_count=sum(1 for r in self._recent_requests if r),
                total_requests=len(self._recent_requests),
                timestamp_state_changed=self._timestamp_state_changed,
                half_open_calls_attempted=self._half_open_attempts,
                failure_rate=self._failure_rate(),
                last_failure_message=self._last_failure_message,
                time_until_half_open_seconds=max(0, self._time_until_half_open()),
            )

    def reset(self) -> None:
        """Reset the Circuit Breaker to initial state."""
        with self._lock:
            self._state = BreakerState.CLOSED
            self._timestamp_state_changed = time.time()
            self._recent_requests.clear()
            self._half_open_attempts = 0
            self._last_failure_message = ""
            logger.info("Circuit Breaker reset to CLOSED state")

    # --- Private Methods ---

    def _update_state_if_needed(self) -> None:
        """Check and update state based on current conditions."""
        if self._state == BreakerState.CLOSED:
            if self._should_trip():
                self._transition_to(BreakerState.OPEN)

        elif (
            self._state == BreakerState.OPEN
            and self._time_since_state_change() >= self._config.open_timeout_seconds
        ):
            self._transition_to(BreakerState.HALF_OPEN)
            self._half_open_attempts = 0

        # HALF_OPEN state transitions are handled in record_success/record_failure

    def _should_trip(self) -> bool:
        """Check if the breaker should trip to OPEN state."""
        if len(self._recent_requests) < self._config.window_size // 2:
            # Not enough data yet
            return False
        return self._failure_rate() > self._config.failure_rate_threshold

    def _transition_to(self, new_state: BreakerState) -> None:
        """Transition to a new state with logging."""
        if new_state != self._state:
            logger.warning(
                "Circuit Breaker transition: %s -> %s (failure_rate=%.1f%%, window=%d)",
                self._state.value,
                new_state.value,
                self._failure_rate() * 100,
                len(self._recent_requests),
            )
            self._state = new_state
            self._timestamp_state_changed = time.time()

    def _failure_rate(self) -> float:
        """Calculate current failure rate."""
        if not self._recent_requests:
            return 0.0
        failures = sum(1 for r in self._recent_requests if not r)
        return failures / len(self._recent_requests)

    def _half_open_success_rate(self) -> float:
        """Calculate success rate during HALF_OPEN state."""
        if self._half_open_attempts == 0:
            return 1.0
        # Look at the most recent half_open_attempts results
        recent = list(self._recent_requests)[-self._half_open_attempts :]
        successes = sum(1 for r in recent if r)
        return successes / self._half_open_attempts

    def _time_since_state_change(self) -> float:
        """Get time elapsed since last state change."""
        return time.time() - self._timestamp_state_changed

    def _time_until_half_open(self) -> float:
        """Get remaining time until transition to HALF_OPEN."""
        if self._state != BreakerState.OPEN:
            return 0.0
        elapsed = self._time_since_state_change()
        return max(0.0, self._config.open_timeout_seconds - elapsed)


__all__ = ["GlobalCircuitBreaker"]
