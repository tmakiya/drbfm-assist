"""Formatting utilities for DRBFM Workflow Application."""

from typing import Any


def format_reasoning_chains_as_markdown(reasoning_chains: list[str]) -> str:
    """Format reasoning chains as markdown bullet points."""
    if not reasoning_chains:
        return ""
    return "\n".join([f"- {reasoning}" for reasoning in reasoning_chains])


def format_search_history_as_markdown(search_history: list[dict[str, Any]]) -> str:
    """Format search history as markdown bullet points."""
    if not search_history:
        return ""

    lines = []
    for entry in search_history:
        stage = entry.get("stage", "")
        method = entry.get("method", "")
        doc_ids = entry.get("doc_ids", [])

        line = f"- Stage {stage}: {method}"
        if doc_ids:
            line += f" - doc_ids: {', '.join([str(i) for i in doc_ids])}"
        lines.append(line)

    return "\n".join(lines)
