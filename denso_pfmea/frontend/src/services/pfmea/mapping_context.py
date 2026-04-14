"""PFMEA Mapping Context for cleaner parameter passing.

This module provides a context object to simplify parameter passing
throughout the PFMEA mapping process, reducing function complexity
and improving maintainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, eq=True)
class MappingContext:
    """Context information shared throughout the mapping process.

    This immutable context object groups related parameters together,
    making function signatures cleaner and more maintainable.
    """

    # Process identification
    process_name: str = ""
    change_id: str = ""

    # Candidate lists for reference
    functions: tuple[str, ...] = field(default_factory=tuple)
    assurances: tuple[str, ...] = field(default_factory=tuple)
    requirements: tuple[str, ...] = field(default_factory=tuple)

    # Retry and recovery information
    retry_attempt: int = 0
    recovery_method: str = ""  # "retry", "chunk", "placeholder"
    chunk_info: dict[str, Any] = field(default_factory=dict)

    # Current requirement being processed (for _resolve_index)
    current_requirement_index: int = 0
    current_requirement_text: str = ""
    current_ai_entry: dict[str, Any] = field(default_factory=dict)

    # Model information
    model_name: str = ""
    session_id: str = ""

    def with_requirement(
        self,
        *,
        index: int,
        text: str,
        ai_entry: dict[str, Any] | None = None,
    ) -> MappingContext:
        """Create a new context with updated requirement information.

        This is a convenience method to avoid using dataclasses.replace directly.
        """
        from dataclasses import replace

        return replace(
            self,
            current_requirement_index=index,
            current_requirement_text=text,
            current_ai_entry=ai_entry or {},
        )

    def with_retry(
        self,
        *,
        attempt: int,
        method: str = "retry",
    ) -> MappingContext:
        """Create a new context with updated retry information."""
        from dataclasses import replace

        return replace(
            self,
            retry_attempt=attempt,
            recovery_method=method,
        )

    def with_chunk(
        self,
        *,
        chunk_size: int,
        chunk_index: int,
        total_chunks: int,
    ) -> MappingContext:
        """Create a new context with chunk processing information."""
        from dataclasses import replace

        return replace(
            self,
            recovery_method="chunk",
            chunk_info={
                "chunk_size": chunk_size,
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
            },
        )


__all__ = ["MappingContext"]
