"""Adaptive concurrency limiter based on Circuit Breaker state."""

from __future__ import annotations

from .global_breaker import GlobalCircuitBreaker
from .models import BreakerState


class AdaptiveConcurrencyLimiter:
    """
    Dynamically adjusts concurrency based on Circuit Breaker state.

    When the Circuit Breaker is:
    - CLOSED: Full concurrency (base_workers)
    - HALF_OPEN: Reduced concurrency (50% of base)
    - OPEN: Minimal concurrency (1 worker)

    This prevents thundering herd effects when recovering from rate limiting.

    Usage:
        breaker = get_global_breaker()
        limiter = AdaptiveConcurrencyLimiter(breaker, base_workers=20)

        # Get effective workers for ThreadPoolExecutor
        max_workers = limiter.get_effective_max_workers()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            ...
    """

    def __init__(
        self,
        breaker: GlobalCircuitBreaker,
        base_workers: int = 20,
    ) -> None:
        """
        Initialize the adaptive limiter.

        Args:
            breaker: The Circuit Breaker to monitor
            base_workers: Maximum workers when circuit is CLOSED
        """
        self._breaker = breaker
        self._base_workers = max(1, base_workers)

    @property
    def base_workers(self) -> int:
        """Get the base (maximum) worker count."""
        return self._base_workers

    def get_effective_max_workers(self) -> int:
        """
        Get the effective max_workers based on current Circuit Breaker state.

        Returns:
            - CLOSED: base_workers (full concurrency)
            - HALF_OPEN: base_workers // 2 (reduced concurrency)
            - OPEN: 1 (minimal concurrency)
        """
        state = self._breaker.get_state()

        if state == BreakerState.CLOSED:
            return self._base_workers
        elif state == BreakerState.HALF_OPEN:
            # Reduce to 50%
            return max(1, self._base_workers // 2)
        else:  # OPEN
            # Minimal concurrency
            return 1

    def get_backoff_multiplier(self) -> float:
        """
        Get a multiplier for retry delays based on Circuit Breaker state.

        This allows for more conservative retries when the circuit is stressed.

        Returns:
            - CLOSED: 1.0 (normal delays)
            - HALF_OPEN: 1.5 (slightly longer delays)
            - OPEN: 3.0 (much longer delays)
        """
        state = self._breaker.get_state()

        if state == BreakerState.CLOSED:
            return 1.0
        elif state == BreakerState.HALF_OPEN:
            return 1.5
        else:  # OPEN
            return 3.0

    def should_allow_request(self) -> bool:
        """
        Check if a new request should be allowed.

        This is a softer check than check_can_proceed() - it returns False
        instead of raising an exception.
        """
        state = self._breaker.get_state()
        return state != BreakerState.OPEN


__all__ = ["AdaptiveConcurrencyLimiter"]
