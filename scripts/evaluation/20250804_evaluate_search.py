import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import click
import pandas as pd
from dotenv import load_dotenv
from langfuse.langchain import CallbackHandler
from loguru import logger
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

from drassist.chains.drbfm_workflow import DrbfmWorkflow, DrbfmWorkflowState

load_dotenv()
GoogleGenAIInstrumentor().instrument()


def generate_uuid() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


def run_drbfm_assist_workflow(
    change_point: str, part: str = None, thread_id: int = 1, tags: List[str] = None, top_k: int = 5
) -> str:
    """Run DRBFM assist workflow with direct change point input and Langfuse tracking"""
    # Create workflow and config
    drbfm_workflow = DrbfmWorkflow(gemini_model_name="gemini-2.5-flash")
    config = create_langfuse_config(thread_id, tags)

    # Create initial state with direct change point and optional part
    initial_state = DrbfmWorkflowState(change_point=change_point, part=part, top_k=top_k)

    logger.info(f"Starting DRBFM assist workflow with change point: {change_point}")

    # Run workflow with Langfuse tracking
    result = drbfm_workflow.invoke(
        initial_state=initial_state,
        config=config,
    )

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
@click.argument("input_path", type=Path)
@click.argument("output_path", type=Path)
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
def main(input_path: Path, output_path: Path, tags: str, top_k: int):
    """Run DRBFM assist workflow with specified changing point"""
    # Convert comma-separated tags string to list
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    current_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    run_id = generate_uuid()[:8]
    tags_list = [f"{current_date}_evaluation_{run_id}"] + tags_list
    logger.info(f"Running evaluation with run ID: {run_id}")

    df = pd.read_csv(input_path)
    evaluation_records = []
    for _, row in df.iterrows():
        changing_point = row["分解された変更点(手修正)"]
        part = row["項目"]

        # Run DRBFM assist workflow with direct change point input and Langfuse tracking
        result = run_drbfm_assist_workflow(
            change_point=changing_point,
            part=part,
            tags=tags_list + [f"ID:{row['ID']}"],
            top_k=top_k,
        )
        relevant_doc_ids = [r["doc_id"] for r in result["relevant_search_results"]]
        logger.info(f"Relevant document IDs: {relevant_doc_ids}")
        evaluation_records.append(
            {
                "id": row["ID"],
                "run_id": run_id,
                "changing_point": changing_point,
                "part": part,
                "relevant_doc_ids": relevant_doc_ids,
            }
        )

    evaluation_records = pd.DataFrame(evaluation_records)
    evaluation_records.to_csv(output_path, index=False)

    logger.info(f"Evaluation results saved to {output_path}")
    logger.info("\n" + evaluation_records["relevant_doc_ids"].to_string(index=False))


if __name__ == "__main__":
    main()
