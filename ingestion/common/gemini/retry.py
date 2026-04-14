"""Retry utilities for Gemini API calls."""

import logging
from typing import Callable

from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from .exceptions import RETRIABLE_EXCEPTIONS


def create_retry_decorator(
    max_retries: int = 4,
    min_wait: float = 10.0,
    max_wait: float = 80.0,
    max_time: float | None = 300.0,
    operation_name: str = "operation",
) -> Callable:
    """Create a retry decorator with consistent configuration.

    Args:
        max_retries: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        max_time: Maximum total time for all retries (seconds, default: 300).
            Set to None to disable time-based stopping.
        operation_name: Name of operation for logging

    Returns:
        Configured retry decorator

    """
    stop_condition = stop_after_attempt(max_retries)
    if max_time is not None:
        stop_condition = stop_condition | stop_after_delay(max_time)

    return retry(
        stop=stop_condition,
        wait=wait_exponential(min=min_wait, max=max_wait),
        retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
