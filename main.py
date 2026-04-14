from typing import Any, Dict, List

import click
from dotenv import load_dotenv
from langfuse.langchain import CallbackHandler
from loguru import logger
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

from drassist.chains.drbfm_assist import BatchState, DrbfmAssistWorkflow

load_dotenv()
GoogleGenAIInstrumentor().instrument()


def run_drbfm_assist_workflow(
    raw_input: str,
    part: str = None,
    thread_id: int = 1,
    tags: List[str] = None,
    top_k: int = 5,
    search_size: int = 10,
) -> Dict[str, Any]:
    """Run DRBFM assist workflow with raw input and Langfuse tracking"""
    # Create workflow and config
    drbfm_assist_workflow = DrbfmAssistWorkflow()
    config = create_langfuse_config(thread_id, tags)

    drbfm_assist_workflow.compile().get_graph().draw_mermaid_png(
        output_file_path="data/drbfm_assist_workflow_diagram.png"
    )

    # Create initial state with raw input
    initial_state = BatchState(raw_input=raw_input, part=part, top_k=top_k, search_size=search_size)

    logger.info(f"Starting DRBFM assist workflow with raw input: {raw_input[:100]}...")

    # Run workflow with Langfuse tracking
    result = drbfm_assist_workflow.invoke(
        initial_state=initial_state,
        config=config,
    )

    import ipdb

    ipdb.set_trace()

    return result


def create_langfuse_config(thread_id: int = 1, tags: List[str] = None) -> Dict[str, Any]:
    """Create Langfuse configuration for workflow tracking"""
    if tags is None:
        tags = ["drbfm_assist_workflow"]

    langfuse_handler = CallbackHandler()
    return {
        "configurable": {"thread_id": thread_id},
        "callbacks": [langfuse_handler],
        "run_name": "DRBFM Assist Workflow",
        "metadata": {"langfuse_tags": tags},
    }


@click.command()
@click.argument("raw_input", type=str)
@click.option("--part", type=str, help="Optional part input for enhanced search")
@click.option("--thread-id", default=1, type=int, help="Thread ID for workflow tracking")
@click.option(
    "--tags",
    default="drbfm_assist_workflow",
    type=str,
    help="Comma-separated tags for workflow tracking",
)
@click.option(
    "--top-k",
    default=5,
    type=int,
    help="Number of top search results to keep per change point",
)
@click.option(
    "--search-size",
    default=10,
    type=int,
    help="Number of search results to retrieve per search",
)
def main(raw_input: str, part: str, thread_id: int, tags: str, top_k: int, search_size: int):
    """Run DRBFM assist workflow with raw input containing multiple change points"""
    # Convert comma-separated tags string to list
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    # Run DRBFM assist workflow with raw input and Langfuse tracking
    result = run_drbfm_assist_workflow(
        raw_input=raw_input,
        part=part,
        thread_id=thread_id,
        tags=tags_list,
        top_k=top_k,
        search_size=search_size,
    )

    # Process and display results
    logger.info("\n=== DRBFM Assist Workflow Results ===")

    # Display extracted change points
    change_points = result.get("change_points", [])
    logger.info(f"\nExtracted {len(change_points)} change points:")
    for i, cp in enumerate(change_points, 1):
        logger.info(f"  {i}. {cp}")

    # Display per change point results
    per_cp_results = result.get("per_cp_results", [])
    logger.info(f"\nProcessed {len(per_cp_results)} change points:")

    for result_data in per_cp_results:
        cp = result_data.get("change_point", "Unknown")
        relevant_results = result_data.get("relevant_search_results", [])
        estimation_results = result_data.get("estimation_results", {})
        error = result_data.get("error")

        logger.info(f"\n--- Change Point: {cp} ---")

        if error:
            logger.error(f"  Error: {error}")
        else:
            # Display relevant document IDs
            doc_ids = [r["doc_id"] for r in relevant_results]
            logger.info(f"  Relevant documents ({len(doc_ids)}): {doc_ids}")

            defects = []
            for doc_id in doc_ids:
                if doc_id in estimation_results:
                    defects.append(estimation_results[doc_id])
            logger.info(f"  Estimated defects ({len(defects)})")


if __name__ == "__main__":
    main()
