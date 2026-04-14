"""Evaluate and compare different search workflows (HyDE, Keyword, Keyword with Attributes)"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from loguru import logger
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

from drassist.chains.drbfm_workflow import _evaluate_single_result
from drassist.chains.searches.embedding_search import EmbeddingSearchState, EmbeddingSearchSubGraph
from drassist.chains.searches.hyde_search import HyDESearchGraph, HyDESearchState
from drassist.chains.searches.keyword_search import SearchState, SearchSubGraph
from drassist.chains.searches.keyword_search_with_attributes import (
    SearchWithAttributes,
    SearchWithPartSubGraph,
)
from drassist.llm import GeminiClient

load_dotenv()
GoogleGenAIInstrumentor().instrument()


def generate_uuid() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


def create_langfuse_config(workflow_name: str, thread_id: int = 1, tags: List[str] = None) -> Dict[str, Any]:
    """Create Langfuse configuration for workflow tracking"""
    if tags is None:
        tags = ["search_workflow_evaluation"]

    langfuse_handler = CallbackHandler()
    return {
        "configurable": {"thread_id": thread_id},
        "callbacks": [langfuse_handler],
        "run_name": workflow_name,
        "metadata": {"langfuse_tags": tags},
    }


def evaluate_search_results(
    search_results: List[Dict[str, Any]],
    change_point: str,
    gemini_client: GeminiClient,
    langfuse_client: Langfuse,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Evaluate search results and return relevant doc_ids and evaluation details"""
    if not search_results:
        logger.warning("No search results to evaluate")
        return [], []

    logger.info(f"Evaluating {len(search_results)} search results")

    # Get Langfuse prompt for relevance evaluation
    langfuse_prompt = langfuse_client.get_prompt("Evaluate relevance")
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    evaluation_results = []
    relevant_doc_ids = []

    # Use ThreadPoolExecutor for parallel evaluation
    max_workers = min(8, len(search_results))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all evaluation tasks
        future_to_index = {}
        for i, result in enumerate(search_results):
            future = executor.submit(
                _evaluate_single_result,
                result,
                i,
                change_point,
                gemini_client,
                system_instruction,
                response_schema,
                set(),  # empty set for existing_doc_ids since we're not checking duplicates here
            )
            future_to_index[future] = i

        # Collect results as they complete
        for future in as_completed(future_to_index):
            evaluation_result = future.result()
            evaluation_results.append(evaluation_result)

            # Collect relevant doc_ids
            if evaluation_result.get("is_positive", False) and "skip_reason" not in evaluation_result:
                relevant_doc_ids.append(evaluation_result["doc_id"])

    # Sort evaluation results by result_index to maintain original order
    evaluation_results.sort(key=lambda x: x["result_index"])

    logger.info(f"Found {len(relevant_doc_ids)} relevant results out of {len(search_results)}")
    return relevant_doc_ids, evaluation_results


def run_hyde_search_with_evaluation(
    change_point: str,
    part: Optional[str],
    top_k: int,
    gemini_client: GeminiClient,
    langfuse_client: Langfuse,
    tags: List[str],
) -> Tuple[List[str], float, List[Dict[str, Any]]]:
    """Run HyDE search workflow and evaluate results"""
    start_time = time.time()

    hyde_search_graph = HyDESearchGraph()
    compiled_workflow = hyde_search_graph.compile()

    logger.info(f"Running HyDE search for change point: {change_point}")

    # Run HyDE search workflow
    hyde_search_state = HyDESearchState(query=change_point)
    config = create_langfuse_config("HyDE Search Evaluation", tags=tags)

    search_result = compiled_workflow.invoke(hyde_search_state, config=config)

    # Extract top_k results
    search_results = search_result.get("search_results", [])[:top_k]

    # Evaluate relevance
    relevant_doc_ids, evaluation_results = evaluate_search_results(
        search_results, change_point, gemini_client, langfuse_client
    )

    execution_time = time.time() - start_time
    logger.info(
        f"HyDE search completed in {execution_time:.2f}s with {len(relevant_doc_ids)} relevant results"
    )

    return relevant_doc_ids, execution_time, evaluation_results


def run_keyword_search_with_evaluation(
    change_point: str,
    part: Optional[str],
    top_k: int,
    gemini_client: GeminiClient,
    langfuse_client: Langfuse,
    tags: List[str],
) -> Tuple[List[str], float, List[Dict[str, Any]]]:
    """Run Keyword search workflow and evaluate results"""
    start_time = time.time()

    search_subgraph = SearchSubGraph()
    compiled_workflow = search_subgraph.compile()

    logger.info(f"Running Keyword search for change point: {change_point}")

    # Run search workflow
    search_state = SearchState(query=change_point)
    config = create_langfuse_config("Keyword Search Evaluation", tags=tags)

    search_result = compiled_workflow.invoke(search_state, config=config)

    # Extract top_k results
    search_results = search_result.get("search_results", [])[:top_k]

    # Evaluate relevance
    relevant_doc_ids, evaluation_results = evaluate_search_results(
        search_results, change_point, gemini_client, langfuse_client
    )

    execution_time = time.time() - start_time
    logger.info(
        f"Keyword search completed in {execution_time:.2f}s with {len(relevant_doc_ids)} relevant results"
    )

    return relevant_doc_ids, execution_time, evaluation_results


def run_keyword_search_with_attributes_evaluation(
    change_point: str,
    part: Optional[str],
    top_k: int,
    gemini_client: GeminiClient,
    langfuse_client: Langfuse,
    tags: List[str],
) -> Tuple[List[str], float, List[Dict[str, Any]]]:
    """Run Keyword search with attributes workflow and evaluate results"""
    start_time = time.time()

    search_with_part_subgraph = SearchWithPartSubGraph()
    compiled_workflow = search_with_part_subgraph.compile()

    logger.info(f"Running Keyword search with attributes for change point: {change_point}, part: {part}")

    # Run search workflow with part category filtering
    search_state = SearchWithAttributes(query=change_point, direct_part=part)
    config = create_langfuse_config("Keyword Search with Attributes Evaluation", tags=tags)

    search_result = compiled_workflow.invoke(search_state, config=config)

    # Extract top_k results
    search_results = search_result.get("search_results", [])[:top_k]

    # Evaluate relevance
    relevant_doc_ids, evaluation_results = evaluate_search_results(
        search_results, change_point, gemini_client, langfuse_client
    )

    execution_time = time.time() - start_time
    logger.info(
        f"Keyword search with attributes completed in {execution_time:.2f}s "
        f"with {len(relevant_doc_ids)} relevant results"
    )

    return relevant_doc_ids, execution_time, evaluation_results


def run_embedding_search_with_evaluation(
    change_point: str,
    part: Optional[str],
    top_k: int,
    gemini_client: GeminiClient,
    langfuse_client: Langfuse,
    tags: List[str],
) -> Tuple[List[str], float, List[Dict[str, Any]]]:
    """Run Embedding search workflow and evaluate results"""
    start_time = time.time()

    embedding_search_subgraph = EmbeddingSearchSubGraph()
    compiled_workflow = embedding_search_subgraph.compile()

    logger.info(f"Running Embedding search for change point: {change_point}")

    # Run embedding search workflow
    embedding_search_state = EmbeddingSearchState(query=change_point)
    config = create_langfuse_config("Embedding Search Evaluation", tags=tags)

    search_result = compiled_workflow.invoke(embedding_search_state, config=config)

    # Extract top_k results
    search_results = search_result.get("search_results", [])[:top_k]

    # Evaluate relevance
    relevant_doc_ids, evaluation_results = evaluate_search_results(
        search_results, change_point, gemini_client, langfuse_client
    )

    execution_time = time.time() - start_time
    logger.info(
        f"Embedding search completed in {execution_time:.2f}s with {len(relevant_doc_ids)} relevant results"
    )

    return relevant_doc_ids, execution_time, evaluation_results


def evaluate_workflows_parallel(
    change_point: str,
    part: Optional[str],
    top_k: int,
    gemini_client: GeminiClient,
    langfuse_client: Langfuse,
    tags: List[str],
) -> Dict[str, Any]:
    """Run all four workflows in parallel and compare results"""
    logger.info(f"Evaluating all workflows for change point: {change_point}")

    results = {}

    # Run all four workflows in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all workflow tasks
        future_to_workflow = {
            executor.submit(
                run_hyde_search_with_evaluation,
                change_point,
                part,
                top_k,
                gemini_client,
                langfuse_client,
                tags + ["hyde_search"],
            ): "hyde",
            executor.submit(
                run_keyword_search_with_evaluation,
                change_point,
                part,
                top_k,
                gemini_client,
                langfuse_client,
                tags + ["keyword_search"],
            ): "keyword",
            executor.submit(
                run_keyword_search_with_attributes_evaluation,
                change_point,
                part,
                top_k,
                gemini_client,
                langfuse_client,
                tags + ["keyword_search_with_attributes"],
            ): "keyword_with_attr",
            executor.submit(
                run_embedding_search_with_evaluation,
                change_point,
                part,
                top_k,
                gemini_client,
                langfuse_client,
                tags + ["embedding_search"],
            ): "embedding",
        }

        # Collect results as they complete
        for future in as_completed(future_to_workflow):
            workflow_name = future_to_workflow[future]
            try:
                relevant_doc_ids, execution_time, evaluation_results = future.result()
                results[workflow_name] = {
                    "relevant_doc_ids": relevant_doc_ids,
                    "execution_time": execution_time,
                    "evaluation_results": evaluation_results,
                }
            except Exception as e:
                logger.error(f"Error in {workflow_name} workflow: {str(e)}")
                results[workflow_name] = {
                    "relevant_doc_ids": [],
                    "execution_time": 0,
                    "evaluation_results": [],
                    "error": str(e),
                }

    # Calculate comparison metrics
    hyde_ids = set(results["hyde"]["relevant_doc_ids"])
    keyword_ids = set(results["keyword"]["relevant_doc_ids"])
    keyword_attr_ids = set(results["keyword_with_attr"]["relevant_doc_ids"])
    embedding_ids = set(results["embedding"]["relevant_doc_ids"])

    # Find common results across all workflows
    common_ids = hyde_ids & keyword_ids & keyword_attr_ids & embedding_ids

    # Format reasonings for each workflow
    def format_reasonings(evaluation_results: List[Dict[str, Any]]) -> str:
        """Format evaluation results as bullet list of doc_id: reasoning"""
        reasonings = []
        for result in evaluation_results:
            if result.get("is_positive", False) and "skip_reason" not in result:
                doc_id = result.get("doc_id", "")
                reasoning = result.get("reasoning", "No reasoning provided")
                reasonings.append(f"- {doc_id}: {reasoning}")
        return "\n".join(reasonings)

    evaluation_record = {
        "changing_point": change_point,
        "part": part,
        "hyde_relevant_doc_ids": list(hyde_ids),
        "keyword_relevant_doc_ids": list(keyword_ids),
        "keyword_with_attr_relevant_doc_ids": list(keyword_attr_ids),
        "embedding_relevant_doc_ids": list(embedding_ids),
        "hyde_relevant_count": len(hyde_ids),
        "keyword_relevant_count": len(keyword_ids),
        "keyword_with_attr_relevant_count": len(keyword_attr_ids),
        "embedding_relevant_count": len(embedding_ids),
        # Add reasoning columns
        "hyde_relevant_reasonings": format_reasonings(results["hyde"]["evaluation_results"]),
        "keyword_relevant_reasonings": format_reasonings(results["keyword"]["evaluation_results"]),
        "keyword_with_attr_relevant_reasonings": format_reasonings(
            results["keyword_with_attr"]["evaluation_results"]
        ),
        "embedding_relevant_reasonings": format_reasonings(results["embedding"]["evaluation_results"]),
    }

    logger.info(
        f"Workflow comparison - HyDE: {len(hyde_ids)}, "
        f"Keyword: {len(keyword_ids)}, "
        f"Keyword+Attr: {len(keyword_attr_ids)}, "
        f"Embedding: {len(embedding_ids)}, "
        f"Common: {len(common_ids)}"
    )

    return evaluation_record


@click.command()
@click.argument("input_path", type=Path)
@click.argument("output_path", type=Path)
@click.option(
    "--tags",
    default="search_workflow_evaluation",
    type=str,
    help="Comma-separated tags for workflow tracking",
)
@click.option(
    "--top-k",
    default=5,
    type=int,
    help="Number of top search results to evaluate per workflow",
)
@click.option(
    "--gemini-model",
    default="gemini-2.5-flash",
    type=str,
    help="Gemini model name to use for evaluation",
)
def main(input_path: Path, output_path: Path, tags: str, top_k: int, gemini_model: str):
    """Evaluate and compare search workflows"""
    # Convert comma-separated tags string to list
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    current_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    run_id = generate_uuid()[:8]
    tags_list = [f"{current_date}_workflow_evaluation_{run_id}"] + tags_list
    logger.info(f"Running workflow evaluation with run ID: {run_id}")

    # Initialize clients
    gemini_client = GeminiClient(model_name=gemini_model)
    langfuse_client = Langfuse()

    # Read input data
    df = pd.read_csv(input_path)
    evaluation_records = []

    for _, row in df.iterrows():
        changing_point = row["分解された変更点(手修正)"]
        part = row.get("項目", None)

        logger.info(f"Processing ID: {row['ID']}")

        # Evaluate all workflows
        evaluation_record = evaluate_workflows_parallel(
            change_point=changing_point,
            part=part,
            top_k=top_k,
            gemini_client=gemini_client,
            langfuse_client=langfuse_client,
            tags=tags_list + [f"ID:{row['ID']}"],
        )

        # Add metadata
        evaluation_record["id"] = row["ID"]
        evaluation_record["run_id"] = run_id

        evaluation_records.append(evaluation_record)

    # Save results
    evaluation_df = pd.DataFrame(evaluation_records)
    evaluation_df.to_csv(output_path, index=False)

    logger.info(f"Evaluation results saved to {output_path}")

    # Print summary statistics
    logger.info("\n=== Evaluation Summary ===")
    logger.info(f"Total evaluations: {len(evaluation_df)}")
    logger.info(f"Average relevant results - HyDE: {evaluation_df['hyde_relevant_count'].mean():.2f}")
    logger.info(f"Average relevant results - Keyword: {evaluation_df['keyword_relevant_count'].mean():.2f}")
    logger.info(
        f"Average relevant results - Keyword+Attr: "
        f"{evaluation_df['keyword_with_attr_relevant_count'].mean():.2f}"
    )
    logger.info(
        f"Average relevant results - Embedding: {evaluation_df['embedding_relevant_count'].mean():.2f}"
    )


if __name__ == "__main__":
    main()
