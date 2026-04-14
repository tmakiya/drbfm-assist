"""Structured logging utilities for Sol_PFMEA.

This module provides structured logging with consistent formatting, context,
and runtime visibility for debugging and observability.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

__all__ = ["get_structured_logger", "configure_logging", "LogContext"]


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured logs with timestamp, level, and context."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with structured information."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context if available
        if hasattr(record, "context"):
            log_data["context"] = record.context

        # Add stage if available
        if hasattr(record, "stage"):
            log_data["stage"] = record.stage

        # Add function name
        if record.funcName and record.funcName != "<module>":
            log_data["function"] = record.funcName

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "context",
                "stage",
            } and not key.startswith("_"):
                log_data["extra"] = log_data.get("extra", {})
                log_data["extra"][key] = value

        return json.dumps(log_data, default=str, ensure_ascii=False)


class LogContext:
    """Context manager for adding structured context to log records."""

    def __init__(self, logger: logging.Logger, **context: Any) -> None:
        """Initialize log context.

        Args:
            logger: Logger instance to attach context to
            **context: Key-value pairs to add as context
        """
        self.logger = logger
        self.context = context
        self.old_factory: Any | None = None

    def __enter__(self) -> LogContext:
        """Enter context and attach context to logger."""
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = self.old_factory(*args, **kwargs)  # type: ignore[misc]
            assert isinstance(record, logging.LogRecord)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and restore original log record factory."""
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)


def configure_logging(
    level: int = logging.INFO,
    *,
    structured: bool = True,
    log_file: str | None = None,
    quiet_loggers: tuple[str, ...] = (
        "httpx",
        "httpcore",
        "google_genai",
        "google_genai.models",
    ),
) -> None:
    """Configure logging for Sol_PFMEA.

    Args:
        level: Logging level (default: INFO)
        structured: Whether to use structured JSON logging (default: True)
        log_file: Optional path to log file for persistent logging
    """
    # Remove existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if structured:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root.addHandler(console_handler)
    root.setLevel(level)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        if structured:
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        root.addHandler(file_handler)

    # Reduce chatter from noisy third-party loggers while still surfacing warnings/errors.
    for logger_name in quiet_loggers:
        logging.getLogger(logger_name).setLevel(max(level, logging.WARNING))


def get_structured_logger(name: str) -> logging.Logger:
    """Get a logger instance for structured logging.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance configured for structured logging
    """
    return logging.getLogger(name)
