"""Integrated DRBFM assist workflow using LangGraph"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from typing import Any, Dict, List, Literal, Optional

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

logger = structlog.stdlib.get_logger(__name__)

from drassist.auth import get_internal_token_from_config, get_tenant_id_from_config
from drassist.chains.base import BaseGraph, BaseGraphState
from drassist.chains.estimate_defects_and_countermeasures import (
    DefectEstimation,
    EstimateDefectsState,
    EstimateDefectsWorkflow,
)
from drassist.embeddings.vertexai_client import VertexAIEmbedder
from drassist.isp.manager import ISPManager
from drassist.isp.query_builder import (
    build_field_filters,
    build_field_keyword_query,
    build_knn_query_with_custom_filters,
)
from drassist.text.normalizer import basic_normalize_text, build_longest_subber


class QueryAttributes(BaseModel):
    """Unit category classification result"""

    unit: str = Field(default="", description="Reasoning for the classification")
    parts: list[str] = Field(
        default=[], description="List of parts associated with the unit"
    )
    change: str = Field(default="", description="Change information from query")


@dataclass
class DrbfmWorkflowContext:
    search_size: int = 20
    top_k: int = 5
    use_unit_filter: bool = True


class DrbfmWorkflowState(BaseGraphState):
    """State for DRBFM workflow with direct change point input"""

    # Input
    change_point: str = Field(..., description="Direct change point input")
    part: Optional[str] = Field(
        default=None, description="Optional part input for enhanced search"
    )

    # Search results
    current_search_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Current search results from the latest search step",
    )
    relevant_search_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Accumulated relevant search results from all search steps",
    )

    # Intermediate state
    query_attributes: Optional[QueryAttributes] = Field(
        None, description="Classified unit category"
    )
    evaluation_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed evaluation results for each search result",
    )
    needs_additional_search: bool = Field(
        default=False, description="Flag indicating if additional search is needed"
    )

    # Defect estimation results
    estimation_results: Dict[str, DefectEstimation] = Field(
        default_factory=dict,
        description="Mapping of doc_id to DefectEstimation with reasoning chains",
    )

    # Search history for debugging
    search_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="Search history for debugging purposes"
    )


def extract_attributes_from_query(
    state: DrbfmWorkflowState,
    gemini_client,
    langsmith_client,
    config_manager,
) -> Dict[str, Any]:
    """Classify unit category from change point and optional direct unit input"""
    logger.info(f"Classifying unit category from change point: {state.change_point}")

    # Get unit list from configuration
    categories = config_manager.get("unit_list")
    unit_list = "\n".join(f"- {category}" for category in categories)

    prompt = langsmith_client.pull_prompt("extract_attributes_from_query")
    response_schema = prompt.schema_["response_schema"]
    system_instruction = prompt.messages[0].format(unit_list=unit_list).content

    # Prepare prompt with change point and optional part information
    prompt_text = f"Query: {state.change_point}"
    if state.part:
        prompt_text = f"Part: {state.part}\n{prompt_text}"

    # Generate structured content using Gemini client
    try:
        result = gemini_client.generate_structured_content(
            prompt=prompt_text,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )
    except json.JSONDecodeError:
        return {
            "query_attributes": None,
            "error": "JSONDecodeError in extract attributes from query",
        }

    # Get normalization dictionary from configuration
    normalized_dict = config_manager.get("normalized_notation_dict", {})
    subber = build_longest_subber(normalized_dict)

    # Apply normalization to cause_part
    cause_parts = result.get("cause_part", [])
    normalized_parts = [subber(basic_normalize_text(part)) for part in cause_parts]

    logger.debug(f"Original cause_parts: {cause_parts}")
    logger.debug(f"Normalized cause_parts: {normalized_parts}")

    # Create UnitCategory object
    query_attributes = QueryAttributes(
        unit=result.get("cause_unit", ""),
        parts=normalized_parts,
        change=result.get("unit_part_change", ""),
    )
    logger.debug(f"Query attributes: {query_attributes}")

    return {
        "query_attributes": query_attributes,
        "error": None,
    }


# ========== Helper functions ==========


def _extract_search_results(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract search results from ISP/Elasticsearch response"""
    search_results = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        result = {
            # ISP may not return _score for all queries
            "score": hit.get("_score", 0.0),
            "doc_id": source.get("doc_id"),
            "original_id": source.get("original_id", ""),
            "part": source.get("part", ""),
            "model_number": source.get("model_number", ""),
            "title": source.get("title", ""),
            "content": source.get("content", ""),
            "cause": source.get("cause", ""),
            "countermeasures": source.get("countermeasures", ""),
            "recurrence_prevention": source.get("recurrence_prevention", ""),
            "failure": source.get("failure", ""),
        }
        search_results.append(result)
    return search_results


def post_process_search_results(
    results: List[Dict[str, Any]],
    search_stage: int,
    search_method: str,
) -> List[Dict[str, Any]]:
    """Apply common post-processing to search results"""
    processed_results = []
    for result in results:
        result["search_stage"] = search_stage
        result["search_method"] = search_method
        processed_results.append(result)
    return processed_results


def add_search_history_entry(
    current_history: List[Dict[str, Any]],
    stage: int,
    method: str,
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Add a search history entry"""
    history_entry = {
        "stage": stage,
        "method": method,
        "doc_ids": [result.get("doc_id") for result in results if result.get("doc_id")],
        "result_count": len(results),
    }
    return current_history + [history_entry]


# ========== Search workflow functions ==========


def execute_keyword_search_with_attributes(
    state,
    config: RunnableConfig,
    runtime: Runtime[DrbfmWorkflowContext],
    config_manager,
    match_type: Literal["match", "match_phrase"] = "match",
    model_numbers: Optional[List[str]] = None,
    search_stage: int = 1,
) -> Dict[str, Any]:
    """Process direct change point and run search with part category filtering"""
    logger.info(
        f"Processing change point for search with attributes: {state.change_point}"
    )

    # Create ISPManager for each node execution to avoid blocking startup
    isp_manager = ISPManager(config_manager)

    # Set internal token for ISP authentication
    internal_token = get_internal_token_from_config(config)
    if internal_token:
        isp_manager.set_internal_token(internal_token)

    # Get tenant_id and construct index name
    tenant_id = get_tenant_id_from_config(config)
    if not tenant_id:
        return {
            "error": "tenant_id not found in config",
            "current_search_results": [],
            "search_history": state.search_history,
        }
    index_name = f"drbfm-assist-defects_{tenant_id}"

    ctx = runtime.context
    query_attributes = state.query_attributes

    # Build filters using the generic function
    field_filters = (
        {"cause.unit": query_attributes.unit} if ctx.use_unit_filter else {}
    )
    filters = build_field_filters(field_filters, model_numbers=model_numbers)

    # Build query using the generic function
    # ISP uses .japanese suffix for full-text search
    query = build_field_keyword_query(
        keywords=query_attributes.parts,
        search_field="cause.part",
        match_type=match_type,
        filters=filters,
        minimum_should_match=1,
        use_japanese_analyzer=True,
    )

    logger.debug(query)

    response = isp_manager.search(query, index_name=index_name, size=ctx.search_size)
    response = _extract_search_results(response)

    # Apply common post-processing
    current_search_results = post_process_search_results(
        response, search_stage, "keyword_search_with_attributes"
    )
    search_history = add_search_history_entry(
        state.search_history,
        search_stage,
        "keyword_search_with_attributes",
        current_search_results,
    )

    logger.info(
        f"Collected {len(current_search_results)} total search results with attributes"
    )

    return {
        "current_search_results": current_search_results,
        "search_history": search_history,
        "error": None,
    }


# ========== Result formatting functions ==========


def format_integrated_results(state) -> Dict[str, Any]:
    """Finalize integrated search results in state"""
    if state.error:
        return {"error": state.error}

    # Count relevant results only
    total_relevant_results = len(state.relevant_search_results)

    logger.info(
        f"Finalized integrated search with {total_relevant_results} relevant results"
    )
    return {"error": None}


# ========== Evaluation functions ==========


def _evaluate_single_result(
    result: Dict[str, Any],
    index: int,
    query_attribute: QueryAttributes,
    relevance_gemini_client,
    relevance_instruction: str,
    relevance_schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate relevance of a single search result using single-stage evaluation"""
    doc_id = result.get("doc_id", "")

    # Create structured prompt format for relevance evaluation
    relevance_prompt = json.dumps(
        {
            "change_point": {
                "unit": query_attribute.unit,
                "part": query_attribute.parts,
                "change": query_attribute.change,
            },
            "failure_record": {
                "unit_part_change": result.get("cause", {}).get("part_change", "N/A")
            },
        },
        ensure_ascii=False,
        indent=2,
    )

    # Generate relevance evaluation using relevance Gemini client (gemini-2.5-pro)
    relevance_result = relevance_gemini_client.generate_structured_content(
        prompt=relevance_prompt,
        response_schema=relevance_schema,
        system_instruction=relevance_instruction,
    )

    is_relevant = relevance_result.get("is_relevant", False)
    reasoning = relevance_result.get("reasoning", "No reasoning provided")

    evaluation_result = {
        "result_index": index,
        "doc_id": doc_id,
        "title": result.get("title", ""),
        "is_positive": is_relevant,
        "reasoning": reasoning,
        "es_score": result.get("score", 0),
    }

    logger.debug(
        f"Result {index}, (doc_id={doc_id}): {is_relevant} - {reasoning[:100]}..."
    )

    return evaluation_result


def evaluate_search_relevance(
    state: DrbfmWorkflowState,
    runtime: Runtime[DrbfmWorkflowContext],
    relevance_gemini_client,
    langsmith_client,
) -> Dict[str, Any]:
    """Evaluate search results relevance to change point using LLM"""
    logger.info(
        f"Evaluating search results relevance for change point: {state.change_point}"
    )
    ctx = runtime.context

    # Get current search results
    search_results = state.current_search_results

    if not search_results:
        logger.warning("No search results to evaluate")
        return {
            "positive_results_count": 0,
            "evaluation_results": [],
            "needs_additional_search": True,
            "error": None,
        }

    # Create set of doc_ids already in relevant_search_results to avoid re-evaluation
    existing_doc_ids = {
        result.get("doc_id")
        for result in state.relevant_search_results
        if result.get("doc_id")
    }

    # Remove duplicates from current_search_results based on doc_id and filter out already evaluated docs
    seen_doc_ids = set()
    deduplicated_results = []
    for result in search_results:
        doc_id = result.get("doc_id")
        # Skip if duplicate in current results
        if doc_id and doc_id in seen_doc_ids:
            continue
        # Skip if already in relevant_search_results
        if doc_id and doc_id in existing_doc_ids:
            continue
        if doc_id:
            seen_doc_ids.add(doc_id)
        deduplicated_results.append(result)

    removed_count = len(search_results) - len(deduplicated_results)
    if removed_count > 0:
        logger.info(
            f"Removed {removed_count} results (duplicates or already evaluated). "
            f"Original: {len(search_results)}, Filtered: {len(deduplicated_results)}"
        )

    search_results = deduplicated_results

    logger.info(f"Found {len(existing_doc_ids)} existing relevant results")

    logger.info(f"Evaluating {len(search_results)} search results")

    # Relevance evaluation prompt
    relevance_prompt = langsmith_client.pull_prompt(
        "decide_whether_change_re-trigger_past_cause"
    )
    relevance_schema = relevance_prompt.schema_["response_schema"]
    relevance_instruction = relevance_prompt.messages[0].content

    evaluation_results = []
    positive_count = 0

    # Use ThreadPoolExecutor for parallel evaluation
    max_workers = min(
        8, len(search_results)
    )  # Limit concurrent requests to avoid rate limits
    max_workers = max(max_workers, 1)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all evaluation tasks
        future_to_index = {}
        for i, result in enumerate(search_results):
            future = executor.submit(
                _evaluate_single_result,
                result,
                i,
                state.query_attributes,
                relevance_gemini_client,
                relevance_instruction,
                relevance_schema,
            )
            future_to_index[future] = i

        # Collect results as they complete
        for future in as_completed(future_to_index):
            evaluation_result = future.result()
            evaluation_results.append(evaluation_result)

            # Count positive results
            if evaluation_result.get("is_positive", False):
                positive_count += 1

    # Sort evaluation results by result_index to maintain original order
    evaluation_results.sort(key=lambda x: x["result_index"])

    needs_additional_search = (
        len(state.relevant_search_results) + positive_count < ctx.top_k
    )

    # Add relevant results to accumulated relevant_search_results (excluding duplicates)
    relevant_results = []
    for i, evaluation_result in enumerate(evaluation_results):
        if evaluation_result["is_positive"]:
            relevant_results.append(search_results[i])

    current_total_relevant = len(state.relevant_search_results) + positive_count
    logger.info(
        f"Evaluation completed: {positive_count}/{len(search_results)} positive results"
    )
    logger.info(
        f"Additional search needed: {needs_additional_search} (current total: {current_total_relevant}, threshold: {ctx.top_k})"  # noqa: E501
    )
    logger.info(
        f"Adding {len(relevant_results)} relevant results to accumulated results"
    )

    return {
        "positive_results_count": positive_count,
        "evaluation_results": state.evaluation_results + evaluation_results,
        "needs_additional_search": needs_additional_search,
        "relevant_search_results": state.relevant_search_results + relevant_results,
        "current_search_results": [],  # Reset current search results after evaluation
        "error": None,
    }


# ========== Workflow routing functions ==========


def determine_whether_to_search(state: DrbfmWorkflowState) -> str:
    """Determine the current search state based on relevant results"""
    if state.query_attributes is None:
        return "end"
    else:
        return "search"


def determine_next_search_stage(
    state: DrbfmWorkflowState, runtime: Runtime[DrbfmWorkflowContext]
) -> str:
    """Determine if additional search is needed based on cumulative relevant results count"""
    ctx = runtime.context
    total_relevant = len(state.relevant_search_results)
    if state.needs_additional_search:
        logger.info(
            f"Additional search needed: {total_relevant} cumulative relevant results < {ctx.top_k} threshold"
        )
        return "next_search_stage"
    else:
        logger.info(
            f"Sufficient relevant results found: {total_relevant} >= {ctx.top_k} threshold"
        )
        return "format_results"


def determine_after_no_attributes_search(state: DrbfmWorkflowState) -> str:
    """Determine next step after evaluating no-attributes search results"""
    total_relevant = len(state.relevant_search_results)
    logger.info(f"Total relevant results after no-attributes search: {total_relevant}")
    return "format_results"


# ========== Embedding search functions ==========


def execute_embedding_search_with_attributes(
    state,
    config: RunnableConfig,
    runtime: Runtime[DrbfmWorkflowContext],
    config_manager,
    embedder: VertexAIEmbedder,
    model_numbers: Optional[List[str]] = None,
    search_stage: int = 1,
) -> Dict[str, Any]:
    """Execute embedding-based search using change point with ISP k-NN search"""
    logger.info(
        f"Processing change point for embedding search with attributes: {state.change_point}"
    )

    # Create ISPManager for each node execution to avoid blocking startup
    isp_manager = ISPManager(config_manager)

    # Set internal token for ISP authentication
    internal_token = get_internal_token_from_config(config)
    if internal_token:
        isp_manager.set_internal_token(internal_token)

    # Get tenant_id and construct index name
    tenant_id = get_tenant_id_from_config(config)
    if not tenant_id:
        return {
            "error": "tenant_id not found in config",
            "current_search_results": state.current_search_results,
            "search_history": state.search_history,
        }
    index_name = f"drbfm-assist-defects_{tenant_id}"

    ctx = runtime.context
    query_attributes = state.query_attributes

    # Generate embedding for the change point
    query_embedding = embedder.generate_embedding(state.change_point)

    # Build filters using the generic function
    field_filters = (
        {"cause.unit": query_attributes.unit} if ctx.use_unit_filter else {}
    )
    filters = build_field_filters(field_filters, model_numbers=model_numbers)

    # Build KNN query using the generic function
    query = build_knn_query_with_custom_filters(
        query_embedding=query_embedding,
        size=ctx.search_size,
        filters=filters,
        field="embedding",
        num_candidates=max(ctx.search_size * 10, 100),
    )

    response = isp_manager.search(query, index_name=index_name, size=ctx.search_size)
    response = _extract_search_results(response)

    # Apply common post-processing
    current_search_results = post_process_search_results(
        response, search_stage, "embedding_search_with_attributes"
    )
    search_history = add_search_history_entry(
        state.search_history,
        search_stage,
        "embedding_search_with_attributes",
        current_search_results,
    )

    logger.info(
        f"Collected {len(current_search_results)} total embedding search results with attributes"
    )

    return {
        "current_search_results": state.current_search_results + current_search_results,
        "search_history": search_history,
        "error": None,
    }


# ========== Defect estimation functions ==========


def estimate_defects_and_countermeasures(
    state: DrbfmWorkflowState, estimate_defects_subgraph
) -> Dict[str, Any]:
    """Estimate defects and countermeasures for relevant search results"""
    logger.info(
        f"Estimating defects and countermeasures for {len(state.relevant_search_results)} relevant results"
    )

    if not state.relevant_search_results:
        logger.warning("No relevant search results to estimate defects for")
        return {
            "estimation_results": [],
            "error": None,
        }

    # Create state for EstimateDefectsWorkflow
    estimate_state = EstimateDefectsState(
        change_point=state.change_point,
        search_results=state.relevant_search_results,
    )

    # Compile and run the workflow
    compiled_workflow = estimate_defects_subgraph.compile()
    result = compiled_workflow.invoke(
        estimate_state, config={"run_name": "Estimate Defects and Countermeasures"}
    )

    # Extract estimation results from the result
    estimation_results = result.get("estimation_results", [])

    logger.info(f"Estimated defects for {len(estimation_results)} search results")

    return {
        "estimation_results": estimation_results,
        "error": None,
    }


class DrbfmWorkflow(BaseGraph):
    """DRBFM workflow with direct change point input (skipping extraction)"""

    def __init__(
        self,
        config_path: str = "configs/6307204b.yaml",
        gemini_model_name: str = "gemini-2.5-pro",
    ):
        super().__init__(config_path, gemini_model_name)
        self._search_subgraph = None
        self._embedding_search_subgraph = None
        self._estimate_defects_subgraph = None
        self._gemini_client_for_evaluate = None
        self._embedder = None

    @property
    def state_class(self) -> type[BaseGraphState]:
        return DrbfmWorkflowState

    @property
    def estimate_defects_subgraph(self) -> EstimateDefectsWorkflow:
        if self._estimate_defects_subgraph is None:
            self._estimate_defects_subgraph = EstimateDefectsWorkflow(
                config_path=self._config_path, gemini_model_name="gemini-2.5-pro"
            )
        return self._estimate_defects_subgraph

    @property
    def isp_manager(self) -> ISPManager:
        if self._es_manager is None:
            self._es_manager = ISPManager(self.config_manager)
        return self._es_manager

    @property
    def embedder(self) -> VertexAIEmbedder:
        if self._embedder is None:
            self._embedder = VertexAIEmbedder()
        return self._embedder

    # TODO: multiple gemini model_version in 1 workflow
    @property
    def gemini_client_for_evaluate(self):
        """Get or create GeminiClient instance"""
        if self._gemini_client_for_evaluate is None:
            from drassist.llm import GeminiClient

            self._gemini_client_for_evaluate = GeminiClient(
                model_name="gemini-2.5-pro",
                location="us-central1",
                temperature=0.0,
                seed=42,
            )
        return self._gemini_client_for_evaluate

    def create_workflow(self) -> StateGraph:
        """Create the direct change point workflow graph with agentic search decision"""
        workflow = StateGraph(
            DrbfmWorkflowState, context_schema=DrbfmWorkflowContext
        )

        # Load model numbers from configuration
        confidential_model_numbers = self.config_manager.get(
            "model_numbers.confidential", []
        )
        production_model_numbers = self.config_manager.get(
            "model_numbers.production", []
        )
        model_numbers = confidential_model_numbers + production_model_numbers

        evaluate_relevance_func = partial(
            evaluate_search_relevance,
            relevance_gemini_client=self.gemini_client_for_evaluate,
            langsmith_client=self.langsmith_client,
        )

        # Add nodes with injected dependencies
        # Add classify_unit_category node at the beginning
        workflow.add_node(
            "extract_attributes_from_query",
            partial(
                extract_attributes_from_query,
                gemini_client=self.gemini_client,
                langsmith_client=self.langsmith_client,
                config_manager=self.config_manager,
            ),
        )

        # with attributes search stage_1
        workflow.add_node(
            "execute_keyword_search_with_attributes_stage_1",
            partial(
                execute_keyword_search_with_attributes,
                config_manager=self.config_manager,
                match_type="match_phrase",
                model_numbers=model_numbers,  # Stage 1: with model filter
                search_stage=1,
            ),
        )
        workflow.add_node(
            "evaluate_search_relevance_with_attributes_stage_1", evaluate_relevance_func
        )

        # with attributes search stage_2
        workflow.add_node(
            "execute_keyword_search_with_attributes_stage_2",
            partial(
                execute_keyword_search_with_attributes,
                config_manager=self.config_manager,
                match_type="match",
                model_numbers=model_numbers,
                search_stage=2,
            ),
        )
        workflow.add_node(
            "evaluate_search_relevance_with_attributes_stage_2", evaluate_relevance_func
        )

        # with attributes search stage_3
        workflow.add_node(
            "execute_embedding_search_with_attributes_stage_3",
            partial(
                execute_embedding_search_with_attributes,
                config_manager=self.config_manager,
                embedder=self.embedder,
                model_numbers=model_numbers,
                search_stage=3,
            ),
        )
        workflow.add_node(
            "evaluate_search_relevance_with_attributes_stage_3", evaluate_relevance_func
        )

        # Add estimate defects node
        workflow.add_node(
            "estimate_defects_and_countermeasures",
            partial(
                estimate_defects_and_countermeasures,
                estimate_defects_subgraph=self.estimate_defects_subgraph,
            ),
        )

        workflow.add_node("format_results", format_integrated_results)

        # Add edges - start with extract_attributes_from_query, then proceed to search
        workflow.add_edge(START, "extract_attributes_from_query")
        workflow.add_conditional_edges(
            "extract_attributes_from_query",
            determine_whether_to_search,
            {
                "search": "execute_keyword_search_with_attributes_stage_1",
                "end": END,
            },
        )

        workflow.add_edge(
            "execute_keyword_search_with_attributes_stage_1",
            "evaluate_search_relevance_with_attributes_stage_1",
        )

        workflow.add_conditional_edges(
            "evaluate_search_relevance_with_attributes_stage_1",
            determine_next_search_stage,
            {
                "next_search_stage": "execute_keyword_search_with_attributes_stage_2",
                "format_results": "format_results",
            },
        )

        workflow.add_edge(
            "execute_keyword_search_with_attributes_stage_2",
            "evaluate_search_relevance_with_attributes_stage_2",
        )

        workflow.add_conditional_edges(
            "evaluate_search_relevance_with_attributes_stage_2",
            determine_next_search_stage,
            {
                "next_search_stage": "execute_embedding_search_with_attributes_stage_3",
                "format_results": "format_results",
            },
        )
        workflow.add_edge(
            "execute_embedding_search_with_attributes_stage_3",
            "evaluate_search_relevance_with_attributes_stage_3",
        )

        # Connect no-attributes evaluation to estimate defects, then to format results
        workflow.add_edge(
            "evaluate_search_relevance_with_attributes_stage_3", "format_results"
        )

        # TODO: comment-out when need estimate defects and countermeasures
        workflow.add_edge("format_results", "estimate_defects_and_countermeasures")
        workflow.add_edge("estimate_defects_and_countermeasures", END)

        return workflow
