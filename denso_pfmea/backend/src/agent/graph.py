"""PFMEA AI Workflow Graph Definition.

LangGraph-based workflow for PFMEA AI assessment.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.nodes import (
    aggregate_results,
    execute_llm_assessment,
    execute_risk_rating,
    prefetch_pfmea_mappings,
)
from src.agent.state import PfmeaWorkflowState
from src.common.config import configure_backend_logging

# Initialize logging at module load time
configure_backend_logging()


def build_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the PFMEA AI workflow graph.

    Node structure:
    [START]
        ↓
    prefetch_pfmea_mappings    # PFMEA function mapping preparation
        ↓
    execute_llm_assessment     # AI assessment execution
        ↓
    execute_risk_rating        # Risk rating (S/O/D) evaluation
        ↓
    aggregate_results          # Result aggregation
        ↓
    [END]
    """
    workflow = StateGraph(PfmeaWorkflowState)

    # Add nodes
    workflow.add_node("prefetch_mappings", prefetch_pfmea_mappings)
    workflow.add_node("assessment", execute_llm_assessment)
    workflow.add_node("risk_rating", execute_risk_rating)
    workflow.add_node("aggregate", aggregate_results)

    # Add edges (sequential workflow)
    workflow.set_entry_point("prefetch_mappings")
    workflow.add_edge("prefetch_mappings", "assessment")
    workflow.add_edge("assessment", "risk_rating")
    workflow.add_edge("risk_rating", "aggregate")
    workflow.add_edge("aggregate", END)

    return workflow.compile(name="PFMEA AI Workflow")


# Export the compiled graph
graph = build_graph()

__all__ = ["build_graph", "graph"]
