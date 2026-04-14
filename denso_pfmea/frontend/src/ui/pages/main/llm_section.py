"""UI entry point for the LLM results section."""

from __future__ import annotations

from . import llm_coordinator
from .constants import DEFAULT_VERTEX_MODEL, DEFAULT_VERTEX_REGION
from .llm_results_renderer import render_llm_results

# Re-export coordinator entry points for backward compatibility
start_llm_workflow = llm_coordinator.start_llm_workflow


__all__ = [
    "DEFAULT_VERTEX_MODEL",
    "DEFAULT_VERTEX_REGION",
    "render_llm_results",
    "start_llm_workflow",
]
