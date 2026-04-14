"""LLM-powered change point extraction workflow using LangGraph"""

from functools import partial
from typing import Any, Dict, List

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from loguru import logger
from pydantic import BaseModel, Field

from drassist.chains.base import BaseGraph, BaseGraphState
from drassist.llm import GeminiClient

load_dotenv()


class ChangePoint(BaseModel):
    """Individual change point extracted from query"""

    reasoning: str = Field(..., description="Reasoning for this change")
    change_point: str = Field(..., description="The identified change point")


class ChangeExtractionState(BaseGraphState):
    """State for the change extraction workflow"""

    query: str = Field(..., description="User's input query")
    change_points: List[ChangePoint] = Field(default_factory=list, description="Extracted change points")


def extract_change_points(
    state: ChangeExtractionState, gemini_client: GeminiClient, langfuse_client
) -> Dict[str, Any]:
    """Extract change points from user query using Gemini via Vertex AI"""
    logger.info(f"Extracting change points from query: {state.query}")

    langfuse_prompt = langfuse_client.get_prompt("Decompose change points")
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    # Generate structured content using Gemini client
    result = gemini_client.generate_structured_content(
        prompt=state.query,
        response_schema=response_schema,
        system_instruction=system_instruction,
    )

    # Extract change points from result
    change_points_data = result.get("decomposed_change_points", [])
    change_points = []

    for cp_data in change_points_data:
        change_point = ChangePoint(
            reasoning=cp_data.get("reasoning", ""),
            change_point=cp_data.get("change_point", ""),
        )
        change_points.append(change_point)

    logger.info(f"Extracted {len(change_points)} change points")
    for i, cp in enumerate(change_points, 1):
        logger.debug(f"Change point {i}: {cp.change_point}")

    return {
        "change_points": change_points,
        "error": None,
    }


class ChangeExtractionSubGraph(BaseGraph):
    """Change extraction workflow implementation using BaseGraph"""

    def __init__(
        self, config_path: str = "configs/6307204b.yaml", gemini_model_name: str = "gemini-2.5-flash"
    ):
        super().__init__(config_path, gemini_model_name)

    @property
    def state_class(self) -> type[BaseModel]:
        return ChangeExtractionState

    def create_workflow(self) -> StateGraph:
        """Create the change extraction workflow graph"""
        workflow = StateGraph(ChangeExtractionState)

        # Add nodes with injected dependencies
        workflow.add_node(
            "extract_change_points",
            partial(
                extract_change_points,
                gemini_client=self.gemini_client,
                langfuse_client=self.langfuse_client,
            ),
        )

        # Add edges
        workflow.add_edge(START, "extract_change_points")
        workflow.add_edge("extract_change_points", END)

        return workflow


def create_change_extraction_workflow() -> StateGraph:
    """Create the change extraction workflow graph (legacy function)"""
    change_extraction_subgraph = ChangeExtractionSubGraph()
    return change_extraction_subgraph.compile()


if __name__ == "__main__":
    # Example usage
    subgraph = ChangeExtractionSubGraph()
    graph = subgraph.create_workflow()

    # Example state
    initial_state = ChangeExtractionState(query="eBTMのレイアウトおよび制御の改良によりエア抜き作業性を向上")

    # Run the workflow
    workflow = graph.compile()
    result = workflow.invoke(initial_state)
    print(result["change_points"])
    for cp in result["change_points"]:
        print(f"Change Point: {cp.change_point}")
        print(f"Reasoning: {cp.reasoning}")
        print("-" * 40)
