"""DRBFM Batch workflow - processes a list of change points in parallel using Send API.

This workflow receives a list of change points directly (without LLM extraction)
and processes them in parallel using LangGraph's Send API.
"""

from dataclasses import dataclass, field
from functools import partial
from operator import add
from typing import Annotated, Any, Dict, List

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send
from pydantic import Field

from drassist.chains.base import BaseGraph, BaseGraphState
from drassist.chains.drbfm_workflow import (
    DrbfmWorkflow,
    DrbfmWorkflowContext,
    DrbfmWorkflowState,
)

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class DrbfmBatchContext:
    """Context for DrbfmBatchWorkflow."""

    search_size: int = field(
        default=10, metadata={"description": "Number of search results to retrieve"}
    )
    top_k: int = field(
        default=5, metadata={"description": "Number of top results to retrieve"}
    )
    use_unit_filter: bool = field(
        default=False, metadata={"description": "Whether to filter by unit"}
    )


class DrbfmBatchState(BaseGraphState):
    """State for batch processing - receives list of change points directly."""

    # Input: list of change points (not raw text)
    change_points: List[str] = Field(
        default_factory=list, description="List of change points to process"
    )

    # Results aggregation using reducer
    per_cp_results: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="Aggregated results from each change point processing",
    )


def fanout(
    state: DrbfmBatchState, runtime: Runtime[DrbfmBatchContext]
) -> List[Send]:
    """Create Send objects for parallel processing of change points."""
    sends = []
    for i, cp in enumerate(state.change_points):
        params = {
            "cp": cp,
            "index": i,
            "search_size": runtime.context.search_size,
            "top_k": runtime.context.top_k,
            "use_unit_filter": runtime.context.use_unit_filter,
        }
        logger.debug(f"Fanning out for change point {i}: {cp[:50]}...")
        sends.append(Send("run_single_cp", params))

    logger.info(f"Fanning out to {len(sends)} parallel branches")
    return sends


def run_single_cp_wrapper(
    params: Dict[str, Any],
    drbfm_workflow: DrbfmWorkflow,
) -> Dict[str, Any]:
    """Run DrbfmWorkflow for a single change point."""
    cp = params.get("cp")
    index = params.get("index")
    search_size = params.get("search_size")
    top_k = params.get("top_k")
    use_unit_filter = params.get("use_unit_filter", False)

    logger.info(f"Processing change point {index}: {cp[:50]}...")

    # Create input state for DrbfmWorkflow
    child_state = DrbfmWorkflowState(change_point=cp)
    child_context = DrbfmWorkflowContext(
        search_size=search_size, top_k=top_k, use_unit_filter=use_unit_filter
    )

    # Compile and invoke the workflow
    compiled_workflow = drbfm_workflow.compile()
    child_out = compiled_workflow.invoke(child_state, context=child_context)

    # Extract key results
    result = {
        "index": index,
        "change_point": cp,
        "query_attributes": child_out.get("query_attributes"),
        "relevant_search_results": child_out.get("relevant_search_results", []),
        "estimation_results": child_out.get("estimation_results", {}),
        "search_history": child_out.get("search_history", []),
        "error": child_out.get("error"),
    }

    logger.info(f"Completed processing for change point {index}: {cp[:50]}")

    # Return with reducer-compatible format
    return {"per_cp_results": [result]}


def finalize_results(
    state: DrbfmBatchState,
    runtime: Runtime[DrbfmBatchContext],
) -> Dict[str, Any]:
    """Sort results by index and finalize."""
    # Sort by index to maintain original order
    sorted_results = sorted(state.per_cp_results, key=lambda x: x.get("index", 0))

    total_results = len(sorted_results)
    successful_results = sum(1 for r in sorted_results if not r.get("error"))

    logger.info(
        f"Batch processing completed: {successful_results}/{total_results} successful"
    )

    # Log summary for each change point
    for result in sorted_results:
        cp = result.get("change_point", "Unknown")[:50]
        idx = result.get("index", 0)
        num_relevant = len(result.get("relevant_search_results", []))
        num_estimations = len(result.get("estimation_results", {}))
        error = result.get("error")

        if error:
            logger.warning(f"Change point {idx} '{cp}': Failed - {error}")
        else:
            logger.info(
                f"Change point {idx} '{cp}': {num_relevant} relevant results, "
                f"{num_estimations} estimations"
            )

    return {"per_cp_results": sorted_results, "error": None}


class DrbfmBatchWorkflow(BaseGraph):
    """Batch workflow for processing list of change points in parallel.

    Unlike DrbfmAssistWorkflow which extracts change points from raw text using LLM,
    this workflow receives a list of change points directly and processes them
    in parallel using the Send API.
    """

    def __init__(
        self,
        config_path: str = "configs/8d8232f3.yaml",
        gemini_model_name: str = "gemini-2.5-pro",
    ):
        super().__init__(config_path, gemini_model_name)
        self._drbfm_workflow = None

    @property
    def state_class(self) -> type[BaseGraphState]:
        return DrbfmBatchState

    @property
    def drbfm_workflow(self) -> DrbfmWorkflow:
        """Get or create DrbfmWorkflow instance."""
        if self._drbfm_workflow is None:
            self._drbfm_workflow = DrbfmWorkflow(
                config_path=self._config_path, gemini_model_name=self._gemini_model_name
            )
        return self._drbfm_workflow

    def create_workflow(self) -> StateGraph:
        """Create the batch processing workflow graph."""
        workflow = StateGraph(DrbfmBatchState, context_schema=DrbfmBatchContext)

        # Add nodes
        workflow.add_node(
            "run_single_cp",
            partial(run_single_cp_wrapper, drbfm_workflow=self.drbfm_workflow),
        )
        workflow.add_node("finalize_results", finalize_results, defer=True)

        # Fan-out from START using conditional edges
        workflow.add_conditional_edges(START, fanout)

        # All parallel branches lead to finalize_results
        workflow.add_edge("run_single_cp", "finalize_results")
        workflow.add_edge("finalize_results", END)

        return workflow
