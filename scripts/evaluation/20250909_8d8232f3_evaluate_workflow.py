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

from drassist.chains.drbfm_workflow_8d8232f3 import DrbfmWorkflow, DrbfmWorkflowState

load_dotenv()
GoogleGenAIInstrumentor().instrument()


def generate_uuid() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


def run_drbfm_workflow_8d8232f3(
    change_point: str,
    thread_id: int = 1,
    tags: List[str] = None,
    top_k: int = 5,
    search_size: int = 10,
) -> Dict[str, Any]:
    """Run DRBFM workflow 8d8232f3 with change point input and Langfuse tracking"""
    # Create workflow with specific config
    drbfm_workflow = DrbfmWorkflow(config_path="configs/8d8232f3.yaml", gemini_model_name="gemini-2.5-pro")
    config = create_langfuse_config(thread_id, tags)

    # Create initial state with change point
    initial_state = DrbfmWorkflowState(change_point=change_point, top_k=top_k, search_size=search_size)

    logger.info(f"Starting DRBFM workflow 8d8232f3 with change point: {change_point[:100]}...")

    try:
        # Run workflow with Langfuse tracking
        result = drbfm_workflow.invoke(
            initial_state=initial_state,
            config=config,
        )
        return result
    except Exception as e:
        error_msg = f"invoke failed: {str(e)}"
        logger.error(f"DRBFM workflow failed for change point: {change_point[:100]}... Error: {error_msg}")
        return {
            "relevant_search_results": [],
            "estimation_results": {},
            "query_attributes": None,
            "search_history": [],
            "error": error_msg,
        }


def create_langfuse_config(thread_id: int = 1, tags: List[str] = None) -> Dict[str, Any]:
    """Create Langfuse configuration for workflow tracking"""
    if tags is None:
        tags = ["drbfm_workflow_8d8232f3"]

    langfuse_handler = CallbackHandler()
    return {
        "configurable": {"thread_id": thread_id},
        "callbacks": [langfuse_handler],
        "run_name": "DRBFM Workflow 8d8232f3",
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


def create_output_rows(input_row: pd.Series, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create output rows from simplified CSV input (ID, 変更)"""
    output_rows = []

    # Extract input data (simplified)
    input_id = input_row["ID"]
    change_point = input_row["変更"]

    # Extract workflow results
    search_results = result.get("relevant_search_results", [])
    estimation_results = result.get("estimation_results", {})
    query_attributes = result.get("query_attributes", None)
    search_history = result.get("search_history", [])
    search_history_markdown = format_search_history_as_markdown(search_history)
    error = result.get("error")

    if error:
        logger.warning(f"Error detected in workflow result: {error}")

    # If no search results, create one row with empty search result fields
    if not search_results:
        output_row = {
            "ID": input_id,
            "変更": change_point,
            "クエリ_ユニット": query_attributes.unit if query_attributes else "",
            "クエリ_部位": query_attributes.parts if query_attributes else "",
            "クエリ_変更": query_attributes.change if query_attributes else "",
            "検索履歴": search_history_markdown,
            "検索結果_ID": "",
            "DrawerURL": "",
            "検索ステージ": "",
            "推定不具合_内容": "",
            "推定不具合_原因": "",
            "推定不具合_対策": "",
            "推定不具合_根拠": "",
            "検索方法": "",
            "検索結果_ユニット(cause_unit)": "",
            "検索結果_部位(cause_part)": "",
            "検索結果_変更(unit_part_change)": "",
            "検索結果_故障モード(failure_mode)": "",
            "検索結果_故障影響(failure_effect)": "",
            "検索結果_対策": "",
            "エラー詳細": error or "",
        }
        output_rows.append(output_row)
    else:
        # Create one row per search result
        for result_item in search_results:
            doc_id = result_item.get("doc_id", "")

            # Get estimation result
            estimation_data = {}
            if doc_id in estimation_results:
                estimation_result = estimation_results[doc_id]
                if hasattr(estimation_result, "model_dump"):
                    estimation_data = estimation_result.model_dump()
                else:
                    estimation_data = estimation_result

            output_row = {
                "ID": input_id,
                "変更": change_point,
                "クエリ_ユニット": query_attributes.unit if query_attributes else "",
                "クエリ_部位": query_attributes.parts if query_attributes else "",
                "クエリ_変更": query_attributes.change if query_attributes else "",
                "検索履歴": search_history_markdown,
                "検索結果_ID": doc_id,
                "DrawerURL": f"https://caddi-drawer.com/8d8232f3-010d-4857-bf20-0cc7dc42ad97/documents/{result_item.get('original_id', '')}",  # noqa: E501
                "検索ステージ": result_item.get("search_stage", ""),
                "推定不具合_内容": estimation_data.get("potential_defect", ""),
                "推定不具合_原因": estimation_data.get("potential_cause", ""),
                "推定不具合_対策": estimation_data.get("countermeasure", ""),
                "推定不具合_根拠": format_reasoning_chains_as_markdown(
                    estimation_data.get("reasoning_chains", [])
                ),
                "検索方法": result_item.get("search_method", ""),
                "検索結果_ユニット(cause_unit)": result_item.get("cause", {}).get("unit", ""),
                "検索結果_部位(cause_part)": result_item.get("cause", {}).get("part", ""),
                "検索結果_変更(unit_part_change)": result_item.get("cause", {}).get("part_change", ""),
                "検索結果_故障モード(failure_mode)": result_item.get("failure", {}).get("mode", ""),
                "検索結果_故障影響(failure_effect)": result_item.get("failure", {}).get("effect", ""),
                "検索結果_対策": result_item.get("countermeasures", ""),
                "エラー詳細": error or "",
            }
            output_rows.append(output_row)

    return output_rows


@click.command()
@click.argument("input_path", type=Path)
@click.argument("output_path", type=Path)
@click.option(
    "--tags",
    default="drbfm_workflow_8d8232f3_evaluation",
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
@click.option(
    "--target-ids",
    type=str,
    help="Comma-separated list of target IDs to process (if not specified, all records will be processed)",
)
def main(input_path: Path, output_path: Path, tags: str, top_k: int, search_size: int, target_ids: str):
    """Generate CSV with search results for DRBFM Workflow 8d8232f3 evaluation"""
    logger.add("data/20250909_8d8232f3_workflow_evaluation.log", level="DEBUG")

    # Convert comma-separated tags string to list
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    current_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    run_id = generate_uuid()[:8]
    tags_list = [f"{current_date}_workflow_evaluation_{run_id}"] + tags_list
    logger.info(f"Running workflow evaluation with run ID: {run_id}")

    # Read input data
    df = pd.read_csv(input_path)
    logger.info(f"Loaded {len(df)} rows from {input_path}")

    # Filter by target_ids if specified
    if target_ids:
        target_ids_list = [id.strip() for id in target_ids.split(",") if id.strip()]
        df_filtered = df[df["ID"].astype(str).isin(target_ids_list)]
        logger.info(f"Filtered to {len(df_filtered)} rows based on target_ids: {target_ids_list}")
        if len(df_filtered) == 0:
            logger.warning("No matching records found for the specified target_ids")
            return
        df = df_filtered

    all_output_rows = []

    for idx, row in df.iterrows():
        change_point = row["変更"]
        input_id = row["ID"]

        logger.info(f"Processing row {idx + 1}/{len(df)}: ID={input_id}, 変更={change_point[:50]}...")

        # Run DRBFM workflow 8d8232f3 with change point input and Langfuse tracking
        result = run_drbfm_workflow_8d8232f3(
            change_point=change_point,
            thread_id=idx,
            tags=tags_list + [f"ID:{input_id}"],
            top_k=top_k,
            search_size=search_size,
        )

        # Process results using simplified function
        output_rows = create_output_rows(row, result)
        all_output_rows.extend(output_rows)

        logger.info(f"Generated {len(output_rows)} output rows for ID: {input_id}")

    # Create output DataFrame
    output_df = pd.DataFrame(all_output_rows)

    # Save to CSV
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    logger.info(f"Evaluation results saved to {output_path}")
    logger.info(f"Total output rows: {len(output_df)}")

    # Summary statistics
    total_inputs = len(df)
    total_search_results = len(output_df[output_df["検索結果_ID"] != ""])

    logger.info("\n=== Summary ===")
    logger.info(f"Total inputs: {total_inputs}")
    logger.info(f"Total search results: {total_search_results}")


if __name__ == "__main__":
    main()
