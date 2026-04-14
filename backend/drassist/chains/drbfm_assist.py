"""DRBFM Assist workflow that processes multiple change points in parallel using map-reduce pattern"""

from dataclasses import dataclass, field
from functools import partial
from operator import add
from typing import Annotated, Any, Dict, List, Optional

from drassist.auth import get_tenant_id_from_config
from drassist.chains.base import BaseGraph, BaseGraphState
from drassist.chains.drbfm_workflow import (
    DrbfmWorkflow,
    DrbfmWorkflowContext,
    DrbfmWorkflowState,
)
import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send
from pydantic import BaseModel, Field

logger = structlog.stdlib.get_logger(__name__)


class ChangePointData(BaseModel):
    """Single change point extracted from input"""

    change_point: str = Field(..., description="The identified change point")
    reasoning: str = Field(..., description="Reasoning for this change")


@dataclass
class DrbfmAssistWorkflowContext:
    """Context for DrbfmAssistWorkflow"""

    search_size: int = field(
        default=10, metadata={"description": "Number of search results to retrieve"}
    )
    top_k: int = field(
        default=5, metadata={"description": "Number of top results to retrieve"}
    )


class DrbfmAssistWorkflowState(BaseGraphState):
    """State for batch processing multiple change points"""

    # Input
    raw_input: str = Field(
        default="", description="Raw input text containing multiple change points"
    )
    part: Optional[str] = Field(
        None, description="Optional part input for enhanced search"
    )

    # Intermediate
    change_points: List[str] = Field(
        default_factory=list, description="List of extracted change points"
    )

    # Results aggregation using reducer
    per_cp_results: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="Aggregated results from each change point processing",
    )


def split_change_points(
    state: DrbfmAssistWorkflowState,
    runtime: Runtime[DrbfmAssistWorkflowContext],
    gemini_client,
    langsmith_client,
) -> Dict[str, Any]:
    """Split raw input into individual change points using LLM"""
    logger.info(f"Splitting raw input into change points: {state.raw_input[:100]}...")

    # Get LangSmith prompt for decomposing change points
    prompt = langsmith_client.pull_prompt("decompose_change_points")
    response_schema = prompt.schema_["response_schema"]
    system_instruction = prompt.messages[0].content

    # Construct prompt
    prompt_text = f"Content: {state.raw_input}"
    if state.part:
        prompt_text = f"Part: {state.part}\n\n{prompt_text}"

    # Generate structured content using Gemini
    result = gemini_client.generate_structured_content(
        prompt=prompt_text,
        response_schema=response_schema,
        system_instruction=system_instruction,
    )

    # Extract change points
    change_points = []
    for cp_data in result.get("decomposed_change_points", []):
        change_point = cp_data.get("change_point", "")
        if change_point:
            change_points.append(change_point)
            logger.debug(f"Extracted change point: {change_point}")

    logger.info(f"Extracted {len(change_points)} change points from input")

    return {
        "change_points": change_points,
        "error": None,
    }


def run_single_cp_wrapper(
    params: Dict[str, Any],
    drbfm_workflow: DrbfmWorkflow,
) -> Dict[str, Any]:
    """Run DrbfmWorkflow for a single change point"""
    cp = params.get("cp")
    part = params.get("part")
    search_size = params.get("search_size")
    top_k = params.get("top_k")

    logger.info(f"Processing change point: {cp}")

    # Create input state for DrbfmWorkflow
    child_state = DrbfmWorkflowState(
        change_point=cp,
        part=part,
    )
    child_context = DrbfmWorkflowContext(search_size=search_size, top_k=top_k)

    # Run the workflow
    # Compile and invoke the workflow
    compiled_workflow = drbfm_workflow.compile()
    child_out = compiled_workflow.invoke(child_state, context=child_context)

    # Extract key results
    result = {
        "change_point": cp,
        "change_point_attributes": child_out.get("query_attributes"),
        "relevant_search_results": child_out.get("relevant_search_results", []),
        "estimation_results": child_out.get("estimation_results", {}),
        "search_history": child_out.get("search_history", []),
        "error": child_out.get("error"),
    }

    logger.info(f"Completed processing for change point: {cp}")

    # Return with reducer-compatible format
    return {"per_cp_results": [result]}


def fanout(
    state: DrbfmAssistWorkflowState, runtime: Runtime[DrbfmAssistWorkflowContext]
) -> List[Send]:
    """Create Send objects for parallel processing of change points"""
    sends = []
    for cp in state.change_points:
        # Create separate state for each change point
        params = {
            "cp": cp,
            "part": state.part,
            "search_size": runtime.context.search_size,
            "top_k": runtime.context.top_k,
        }
        logger.debug(f"Fanning out for change point: {cp}")
        sends.append(Send("run_single_cp", params))

    logger.info(f"Fanning out to {len(sends)} parallel branches")
    return sends


def format_batch_results(
    state: DrbfmAssistWorkflowState,
    runtime: Runtime[DrbfmAssistWorkflowContext],
) -> Dict[str, Any]:
    """Format the aggregated results from all change points"""
    total_results = len(state.per_cp_results)
    successful_results = sum(1 for r in state.per_cp_results if not r.get("error"))

    logger.info(
        f"Batch processing completed: {successful_results}/{total_results} successful"
    )

    # Log summary for each change point
    for result in state.per_cp_results:
        cp = result.get("change_point", "Unknown")
        num_relevant = len(result.get("relevant_search_results", []))
        num_estimations = len(result.get("estimation_results", {}))
        error = result.get("error")

        if error:
            logger.warning(f"Change point '{cp}': Failed - {error}")
        else:
            logger.info(
                f"Change point '{cp}': {num_relevant} relevant results, {num_estimations} estimations"
            )

    return {"error": None}


class DrbfmAssistWorkflow(BaseGraph):
    """Batch workflow for processing multiple change points in parallel"""

    def __init__(
        self,
        config_path: str = "configs/6307204b.yaml",
        gemini_model_name: str = "gemini-2.5-flash",
    ):
        super().__init__(config_path, gemini_model_name)
        self._drbfm_workflow = None

    @property
    def state_class(self) -> type[BaseGraphState]:
        return DrbfmAssistWorkflowState

    @property
    def drbfm_workflow(self) -> DrbfmWorkflow:
        """Get or create DrbfmWorkflow instance"""
        if self._drbfm_workflow is None:
            self._drbfm_workflow = DrbfmWorkflow(
                config_path=self._config_path, gemini_model_name=self._gemini_model_name
            )
        return self._drbfm_workflow

    def create_workflow(self) -> StateGraph:
        """Create the batch processing workflow graph"""
        workflow = StateGraph(
            DrbfmAssistWorkflowState, context_schema=DrbfmAssistWorkflowContext
        )

        # Add nodes
        workflow.add_node(
            "split_change_points",
            partial(
                split_change_points,
                gemini_client=self.gemini_client,
                langsmith_client=self.langsmith_client,
            ),
        )

        workflow.add_node(
            "run_single_cp",
            partial(run_single_cp_wrapper, drbfm_workflow=self.drbfm_workflow),
        )

        workflow.add_node("format_batch_results", format_batch_results, defer=True)

        # Add edges
        workflow.add_edge(START, "split_change_points")

        # Use conditional edges with fanout for parallel processing
        workflow.add_conditional_edges("split_change_points", fanout)

        # All parallel branches lead to format_batch_results
        workflow.add_edge("run_single_cp", "format_batch_results")
        workflow.add_edge("format_batch_results", END)

        return workflow
