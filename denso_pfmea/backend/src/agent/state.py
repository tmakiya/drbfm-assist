"""PFMEA Workflow State Definition for LangGraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PfmeaWorkflowState:
    """Workflow state for PFMEA AI assessment.

    This state is passed through the LangGraph workflow nodes.
    """

    # ===== Input =====
    changes: List[Dict[str, Any]] = field(default_factory=list)
    pfmea_context: Dict[str, Any] = field(default_factory=dict)
    selected_model: str = "gemini-2.5-pro"
    default_model: str = "gemini-2.5-pro"
    default_region: str = "us-central1"

    # ===== Internal (generated within workflow) =====
    function_mappings: Dict[str, Any] = field(default_factory=dict)
    assessment_results: Dict[str, Dict[str, str]] = field(default_factory=dict)
    risk_ratings: Dict[str, Any] = field(default_factory=dict)
    rating_targets_lookup: Dict[str, Any] = field(default_factory=dict)

    # ===== Progress =====
    current_phase: str = "idle"
    completed_count: int = 0
    total_count: int = 0
    phase_message: str = ""

    # ===== Output =====
    structured_rows: List[Dict[str, str]] = field(default_factory=list)
    rows_by_change: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    # ===== Error =====
    error: Optional[str] = None
    error_code: Optional[str] = None


__all__ = ["PfmeaWorkflowState"]
