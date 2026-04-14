"""Circuit Breaker pattern for LLM rate limiting protection.

This module provides a Circuit Breaker implementation to protect against
cascading failures when the LLM service is rate-limited.

Components:
- GlobalCircuitBreaker: Monitors failure rates and controls circuit state
- AdaptiveConcurrencyLimiter: Adjusts parallel worker count based on state
- BreakerConfig/BreakerMetrics: Configuration and observability

Usage:
    from src.services.circuit_breaker import (
        get_global_breaker,
        AdaptiveConcurrencyLimiter,
    )

    breaker = get_global_breaker()
    limiter = AdaptiveConcurrencyLimiter(breaker, base_workers=20)

    # Check before making LLM call
    try:
        breaker.check_can_proceed()
        result = make_llm_call()
        breaker.record_success()
    except CircuitOpenError:
        # Circuit is open, skip this request
        pass
    except RateLimitError:
        breaker.record_failure(is_rate_limit=True)
        raise
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .adaptive_limiter import AdaptiveConcurrencyLimiter
from .global_breaker import GlobalCircuitBreaker
from .models import (
    BreakerConfig,
    BreakerMetrics,
    BreakerState,
    CircuitBreakerError,
    CircuitOpenError,
)

if TYPE_CHECKING:
    pass

# Global singleton instance
_GLOBAL_BREAKER: GlobalCircuitBreaker | None = None


def get_global_breaker() -> GlobalCircuitBreaker:
    """Get the global Circuit Breaker instance.

    Returns a singleton instance that is shared across all LLM calls.
    This ensures coordinated rate limiting protection.
    """
    global _GLOBAL_BREAKER
    if _GLOBAL_BREAKER is None:
        _GLOBAL_BREAKER = GlobalCircuitBreaker(
            config=BreakerConfig(
                failure_rate_threshold=0.5,  # Trip at 50% failure rate
                window_size=20,  # Look at last 20 requests
                open_timeout_seconds=30.0,  # Wait 30s before HALF_OPEN
                half_open_max_calls=3,  # Test with 3 calls
                half_open_success_threshold=0.8,  # Need 80% success to close
            )
        )
    return _GLOBAL_BREAKER


def reset_global_breaker() -> None:
    """Reset the global Circuit Breaker.

    Useful for testing or manual recovery.
    """
    global _GLOBAL_BREAKER
    if _GLOBAL_BREAKER is not None:
        _GLOBAL_BREAKER.reset()
    _GLOBAL_BREAKER = None


__all__ = [
    # Classes
    "GlobalCircuitBreaker",
    "AdaptiveConcurrencyLimiter",
    "BreakerConfig",
    "BreakerMetrics",
    "BreakerState",
    # Exceptions
    "CircuitBreakerError",
    "CircuitOpenError",
    # Functions
    "get_global_breaker",
    "reset_global_breaker",
]
