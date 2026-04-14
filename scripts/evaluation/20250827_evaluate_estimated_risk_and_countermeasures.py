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
    change_point: str,
    part: str,
    thread_id: int = 1,
    tags: List[str] = None,
    top_k: int = 5,
    search_size: int = 10,
) -> Dict[str, Any]:
    """Run DRBFM assist workflow with direct change point input and Langfuse tracking"""
    # Create workflow and config
    drbfm_workflow = DrbfmWorkflow(gemini_model_name="gemini-2.5-flash")
    config = create_langfuse_config(thread_id, tags)

    # Create initial state with direct change point and optional part
    initial_state = DrbfmWorkflowState(
        change_point=change_point, part=part, top_k=top_k, search_size=search_size
    )

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


def format_search_history_as_markdown(search_history: List[Dict[str, Any]]) -> str:
    """Format search history as markdown bullet points"""
    if not search_history:
        return ""

    lines = []
    for entry in search_history:
        stage = entry.get("stage", "")
        method = entry.get("method", "")
        doc_ids = entry.get("doc_ids", [])

        # Create bullet point for each search entry
        line = f"- Stage {stage}: {method}"
        if doc_ids:
            line += f" - doc_ids: {', '.join([str(i) for i in doc_ids])}"
        lines.append(line)

    return "\n".join(lines)


def format_reasoning_chains_as_markdown(reasoning_chains: List[str]) -> str:
    """Format reasoning chains as markdown bullet points"""
    if not reasoning_chains:
        return ""

    lines = []
    for reasoning in reasoning_chains:
        lines.append(f"- {reasoning}")

    return "\n".join(lines)


def create_output_rows(
    input_row: pd.Series, search_results: List[Dict[str, Any]], state_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Create output rows for each search result, expanding one input row into multiple output rows"""
    output_rows = []

    # Extract input data
    item = input_row["項目"]
    change_point = input_row["分解された変更点"]

    # Extract keywords from search conditions
    keywords = []
    if state_data.get("search_conditions"):
        keywords.extend(state_data["search_conditions"].must or [])
        keywords.extend(state_data["search_conditions"].should or [])

    # Get evaluation results for reasoning
    evaluation_results = state_data.get("evaluation_results", [])
    evaluation_by_doc_id = {
        eval_result.get("doc_id"): eval_result
        for eval_result in evaluation_results
        if eval_result.get("doc_id")
    }

    # Get estimated risk and countermeasures
    estimation_results = state_data.get("estimation_results", {})

    query_attributes = state_data["query_attributes"]
    search_history_markdown = format_search_history_as_markdown(state_data.get("search_history", []))

    # If no search results, create one row with empty search result fields
    if not search_results:
        output_row = {
            "QueryID": input_row["ID"],
            "項目": item,
            "分解された変更点": change_point,
            "クエリ_ユニット": query_attributes.unit,
            "クエリ_部位": query_attributes.parts,
            "クエリ_変更": query_attributes.change,
            "検索履歴": search_history_markdown,
            "検索結果_ID": "",
            "検索ステージ": "",
            "推定不具合_内容": "",
            "推定不具合_原因": "",
            "推定不具合_対策": "",
            "推定不具合_根拠": "",
            "検索方法": "",
            "検索結果_型式": "",
            "検索結果_ユニット(cause_unit)": "",
            "検索結果_部位(cause_part)": "",
            "検索結果_変更(unit_part_change)": "",
            "検索結果_故障モード(failure_mode)": "",
            "検索結果_故障影響(failure_effect)": "",
            "関連判定の根拠": "",
            "表題": "",
            "内容": "",
            "原因": "",
            "対策": "",
            "再発防止": "",
        }
        output_rows.append(output_row)
    else:
        # Create one row per search result
        for result in search_results:
            doc_id = result.get("doc_id", "")

            # Get evaluation reasoning for this document
            eval_result = evaluation_by_doc_id.get(doc_id, {})
            reasoning = eval_result.get("reasoning", "")

            # Get estimation result
            if doc_id in estimation_results:
                estimation_result = estimation_results[doc_id].model_dump()
            else:
                estimation_result = {}

            output_row = {
                "QueryID": input_row["ID"],
                "項目": item,
                "分解された変更点": change_point,
                "クエリ_ユニット": query_attributes.unit,
                "クエリ_部位": query_attributes.parts,
                "クエリ_変更": query_attributes.change,
                "検索履歴": search_history_markdown,
                "検索結果_ID": doc_id,
                "検索ステージ": result.get("search_stage", ""),
                "推定不具合_内容": estimation_result.get("potential_defect", ""),
                "推定不具合_原因": estimation_result.get("potential_cause", ""),
                "推定不具合_対策": estimation_result.get("countermeasure", ""),
                "推定不具合_根拠": format_reasoning_chains_as_markdown(
                    estimation_result.get("reasoning_chains", [])
                ),
                "検索方法": result.get("search_method", ""),
                "検索結果_型式": result.get("model_number", ""),  # Get from search result
                "検索結果_ユニット(cause_unit)": result.get("cause", {}).get("unit", ""),
                "検索結果_部位(cause_part)": result.get("cause", {}).get("part", ""),
                "検索結果_変更(unit_part_change)": result.get("cause", {}).get("part_change", ""),
                "検索結果_故障モード(failure_mode)": result.get("failure", {}).get("mode", ""),
                "検索結果_故障影響(failure_effect)": result.get("failure", {}).get("effect", ""),
                "関連判定の根拠": reasoning,
                "表題": result.get("title", ""),
                "内容": result.get("content", ""),
                "原因": result.get("cause", {}).get("original", ""),
                "対策": result.get("countermeasure", ""),
                "再発防止": result.get("recurrence_prevention", ""),
            }
            output_rows.append(output_row)

    return output_rows


@click.command()
@click.argument("input_path", type=Path, default="./data/drbfm_tadano_dataset.csv")
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
@click.option(
    "--search-size",
    default=20,
    type=int,
    help="Number of search results to retrieve per search",
)
def main(input_path: Path, output_path: Path, tags: str, top_k: int, search_size: int):
    """Generate CSV with search results for each change point, one row per search result"""
    logger.add("data/20250808_search_results_generation.log")

    # Convert comma-separated tags string to list
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    current_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    run_id = generate_uuid()[:8]
    tags_list = [f"{current_date}_search_results_{run_id}"] + tags_list
    logger.info(f"Running search results generation with run ID: {run_id}")

    # Read input data
    df = pd.read_csv(input_path)
    logger.info(f"Loaded {len(df)} rows from {input_path}")

    all_output_rows = []

    for idx, row in df.iterrows():
        changing_point = row["分解された変更点"]
        part = row["項目"]

        logger.info(f"Processing row {idx + 1}/{len(df)}: {changing_point}")

        # Run DRBFM assist workflow with direct change point input and Langfuse tracking
        result = run_drbfm_assist_workflow(
            change_point=changing_point,
            part=part,
            tags=tags_list + [f"ID:{row.get('ID', idx)}"],
            top_k=top_k,
            search_size=search_size,
        )

        # Extract search results
        search_results = result.get("relevant_search_results", [])
        logger.info(f"Found {len(search_results)} relevant search results")

        # Create output rows (one per search result)
        output_rows = create_output_rows(row, search_results, result)
        all_output_rows.extend(output_rows)

        logger.info(f"Generated {len(output_rows)} output rows for this change point")

    # Create output DataFrame
    output_df = pd.DataFrame(all_output_rows)

    # Save to CSV
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    logger.info(f"Search results saved to {output_path}")
    logger.info(f"Total output rows: {len(output_df)}")


if __name__ == "__main__":
    main()
