"""LLM progress tracking and display components.

This module provides progress management for AI inference workflows,
including progress bar rendering, status updates, and stage tracking.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

# Type alias for progress callback function
ProgressCallback = Callable[[int, int, str, str, dict[str, Any] | None], None]

# Progress bar constants
LLM_PROGRESS_BASE = 20

# Stage labels for different workflow phases
PROMPT_STAGE_LABELS = {
    "executing_primary": "エージェントが考え中",
    "executing_secondary": "エージェントがまとめ中",
    "executing_retry": "エージェントが再確認中",
    "mapping": "割り当てを整理中",
    "rating": "リスクを見直し中",
}


def create_progress_tracker(
    total_requests: int,
    base_progress: int = LLM_PROGRESS_BASE,
    final_progress: int = 100,
) -> tuple[Callable[[int, int | None], int], dict[str, str]]:
    """Create a progress value calculator and phase labels.

    Args:
        total_requests: Total number of AI inference requests.
        base_progress: Starting progress percentage (default: 20).
        final_progress: Ending progress percentage (default: 100).

    Returns:
        Tuple of (progress_calculator, phase_labels).
        - progress_calculator: Function to calculate progress percentage.
        - phase_labels: Dictionary mapping phase names to display labels.
    """
    prompt_rounds = 3 if total_requests else 1
    total_units = max(total_requests * prompt_rounds, 1)

    def calculate_progress(completed_units: int, override: int | None = None) -> int:
        """Calculate progress percentage based on completed units.

        Args:
            completed_units: Number of completed workflow units.
            override: Optional explicit progress value to return.

        Returns:
            Progress percentage (0-100).
        """
        if override is not None:
            return override
        if total_units <= 0:
            return final_progress if completed_units else base_progress
        span = max(final_progress - base_progress, 1)
        ratio = max(0.0, min(1.0, completed_units / total_units))
        return base_progress + int(round(ratio * span))

    phase_labels = {
        "prepare": "準備中",
        "initializing": "エージェントが準備中",
        "mapping": "割り当てを整理中",
        "executing": "推定を進行中",
        "executing_primary": "エージェントが考え中",
        "executing_secondary": "エージェントがまとめ中",
        "executing_retry": "エージェントが再確認中",
        "rating": "リスクを見直し中",
        "final": "完了",
    }

    return calculate_progress, phase_labels


def create_progress_emitter(
    total_requests: int,
    total_units: int,
    progress_calculator: Callable[[int, int | None], int],
    phase_labels: dict[str, str],
    progress_callback: ProgressCallback,
) -> Callable[..., None]:
    """Create a progress event emitter function.

    Args:
        total_requests: Total number of AI inference requests.
        total_units: Total workflow units for progress calculation.
        progress_calculator: Function to calculate progress percentage.
        phase_labels: Dictionary mapping phase names to display labels.
        progress_callback: Callback function to invoke with progress updates.

    Returns:
        Progress emitter function that packages and sends progress events.
    """

    def emit_progress(
        phase: str,
        kind: str,
        label: str,
        completed_units: int,
        *,
        progress_override: int | None = None,
        stage_requests: Mapping[str, int] | None = None,
        message_detail: str | None = None,
    ) -> None:
        """Emit a progress update event.

        Args:
            phase: Current workflow phase (e.g., 'mapping', 'rating').
            kind: Event type ('info', 'success', 'error').
            label: Human-readable progress message.
            completed_units: Number of completed workflow units.
            progress_override: Optional explicit progress percentage.
            stage_requests: Optional dict with completed/pending request counts.
        """
        stage_payload = dict(stage_requests or {})
        completed_requests = int(stage_payload.get("completed_requests", 0))
        pending_requests = int(
            stage_payload.get(
                "pending_requests", max(total_requests - completed_requests, 0)
            )
        )

        details = {
            "phase": phase,
            "phase_label": phase_labels.get(phase, ""),
            "total_requests": total_requests,
            "completed_requests": completed_requests,
            "pending_requests": pending_requests,
            "completed_units": completed_units,
            "total_units": total_units,
            "stage_label": PROMPT_STAGE_LABELS.get(phase),
            "progress_value": progress_calculator(completed_units, progress_override),
        }
        if message_detail:
            details["message"] = message_detail
        else:
            details["message"] = label

        progress_callback(
            min(completed_units, total_units),
            total_units,
            label,
            kind,
            details,
        )

    return emit_progress


def render_progress_ui() -> tuple[Any, Any, Any]:
    """Render progress tracking UI components.

    Avoid fragments here because progress updates occur via callbacks and
    fragment reruns can replace elements at the top of the app.
    """
    progress_bar = st.empty()
    status_placeholder = st.empty()
    detail_placeholder = st.empty()
    return progress_bar, status_placeholder, detail_placeholder


def create_progress_renderer(
    progress_bar: Any,
    status_placeholder: Any,
    detail_placeholder: Any,
) -> ProgressCallback:
    """Create a progress rendering callback for Streamlit UI.

    Args:
        progress_bar: Streamlit empty container for progress bar.
        status_placeholder: Streamlit empty container for status messages.
        detail_placeholder: Streamlit empty container for detailed info.

    Returns:
        Progress callback function that updates the UI components.
    """
    last_status_label: str | None = None
    last_status_kind: str | None = None

    def render_progress(
        completed: int,
        total: int,
        label: str,
        kind: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Render progress update to Streamlit UI.

        Args:
            completed: Number of completed units.
            total: Total number of units.
            label: Progress message to display.
            kind: Message type ('info', 'success', 'error').
            details: Optional additional details dictionary.
        """
        nonlocal last_status_label, last_status_kind

        # Calculate progress value
        progress_value: int | None = None
        if details is not None and "progress_value" in details:
            try:
                progress_value = int(details["progress_value"])
            except (TypeError, ValueError):
                progress_value = None

        if progress_value is None:
            fraction = (completed / total) if total else 1
            progress_value = int(round(fraction * 100))

        progress_value = max(0, min(100, progress_value))
        progress_bar.progress(progress_value, text=label)

        # Update status message if changed
        status_text = label
        if details is not None:
            status_text = (
                details.get("stage_label") or details.get("phase_label") or label
            )

        if status_text != last_status_label or kind != last_status_kind:
            if kind == "error":
                status_placeholder.error(status_text)
            elif kind == "success":
                status_placeholder.success(status_text)
            else:
                status_placeholder.info(status_text)
            last_status_label = status_text
            last_status_kind = kind

        # Clear detail placeholder (can be extended for additional info)
        detail_placeholder.empty()

    return render_progress


__all__ = [
    "ProgressCallback",
    "LLM_PROGRESS_BASE",
    "PROMPT_STAGE_LABELS",
    "create_progress_tracker",
    "create_progress_emitter",
    "render_progress_ui",
    "create_progress_renderer",
]
