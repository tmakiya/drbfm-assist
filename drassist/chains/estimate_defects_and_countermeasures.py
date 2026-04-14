"""Estimate potential defects and countermeasures based on change points and search results"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph
from loguru import logger
from pydantic import BaseModel, Field

from drassist.chains.base import BaseGraph, BaseGraphState


class DefectEstimation(BaseModel):
    """Single defect estimation with risk and countermeasure"""

    reasoning_chains: List[str] = Field(
        ..., description="Logical steps connecting change to potential defect"
    )
    potential_cause: str = Field(..., description="Potential cause of the predicted defect")
    potential_defect: str = Field(..., description="Description of the anticipated risk")
    countermeasure: str = Field(..., description="Corresponding countermeasure for the risk")


class EstimateDefectsState(BaseGraphState):
    """State for defect estimation workflow"""

    # Input
    change_point: str = Field(..., description="Change point description")
    search_results: List[Dict[str, Any]] = Field(..., description="Search results from DRBFM workflow")

    # Processing
    estimation_results: Dict[int, DefectEstimation] = Field(
        default_factory=dict, description="Mapping of doc_id to DefectEstimation"
    )

    # Output
    final_results: List[Dict[str, Any]] = Field(default_factory=list, description="Integrated final results")


def estimate_defects_for_each_result(
    state: EstimateDefectsState,
    gemini_client,
    langfuse_client,
    tenant_id: str,
) -> Dict[str, Any]:
    """Estimate defects for each search result in parallel"""
    logger.info(f"Starting defect estimation for {len(state.search_results)} search results")

    # Get prompt and response schema from Langfuse
    langfuse_prompt = langfuse_client.get_prompt("Estimate defects and countermeasures", label=tenant_id)
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    def process_single_result(search_result: Dict[str, Any]) -> tuple[str, DefectEstimation]:
        """Process a single search result and return (doc_id, DefectEstimation) tuple"""
        # Extract relevant fields with new JSON structure
        failure_data = search_result.get("failure", {})
        prompt_data = {
            "new_change_point": state.change_point,
            "retriggerable_past_failure": {
                "unit": search_result.get("cause", {}).get("unit", ""),
                "part": search_result.get("cause", {}).get("part", ""),
                "part_change": search_result.get("cause", {}).get("part_change", ""),
                "failure": {
                    "mode": failure_data.get("mode", ""),
                    "effect": failure_data.get("effect", ""),
                },
                "countermeasures": search_result.get("countermeasures", ""),
            },
        }

        # Create prompt with new JSON structure
        prompt = json.dumps(prompt_data, ensure_ascii=False, indent=2)

        logger.debug(prompt)

        # Generate estimation using Gemini
        raw_estimation = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        # Create DefectEstimation object
        doc_id = search_result.get("doc_id", "unknown")
        estimation = DefectEstimation(
            reasoning_chains=raw_estimation.get("reasoning_chains", []),
            potential_cause=raw_estimation.get("potential_cause", ""),
            potential_defect=raw_estimation.get("potential_defect", ""),
            countermeasure=raw_estimation.get("countermeasure", ""),
        )
        return (doc_id, estimation)

    # Process all search results in parallel
    # TODO: max_workers should be parameterized
    estimation_results = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        # Submit all tasks
        future_to_result = {
            executor.submit(process_single_result, result): result for result in state.search_results
        }

        # Collect results as they complete
        for future in as_completed(future_to_result):
            doc_id, estimation = future.result()
            estimation_results[doc_id] = estimation

    logger.info(f"Completed estimation with {len(estimation_results)} total estimations")

    return {
        "estimation_results": estimation_results,  # Current format with reasoning_chains
    }


def format_results(state: EstimateDefectsState) -> Dict[str, Any]:
    """Format the final results"""
    if state.error:
        return {"error": state.error}

    logger.info(f"Formatted {len(state.final_results)} defect estimations")
    return {"error": None}


class EstimateDefectsWorkflow(BaseGraph):
    """Workflow for estimating potential defects and countermeasures"""

    def __init__(self, config_path: str = "configs/6307204b.yaml", gemini_model_name: str = "gemini-2.5-pro"):
        super().__init__(config_path, gemini_model_name)

    @property
    def state_class(self) -> type[BaseGraphState]:
        return EstimateDefectsState

    def create_workflow(self) -> StateGraph:
        """Create the defect estimation workflow"""
        workflow = StateGraph(EstimateDefectsState)

        # Add nodes
        workflow.add_node(
            "estimate_defects",
            partial(
                estimate_defects_for_each_result,
                gemini_client=self.gemini_client,
                langfuse_client=self.langfuse_client,
                tenant_id=self.config_manager.get("tenant_id", "6307204b"),
            ),
        )
        workflow.add_node("format_results", format_results)

        # Add edges
        workflow.add_edge(START, "estimate_defects")
        workflow.add_edge("estimate_defects", "format_results")
        workflow.add_edge("format_results", END)

        return workflow
