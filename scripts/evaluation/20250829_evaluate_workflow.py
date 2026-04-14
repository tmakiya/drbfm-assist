import re
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

from drassist.chains.drbfm_assist import DrbfmAssistWorkflow, DrbfmAssistWorkflowState, DrbfmWorkflowContext

load_dotenv()
GoogleGenAIInstrumentor().instrument()


def generate_uuid() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


def run_drbfm_assist_workflow(
    raw_input: str,
    part: str = None,
    thread_id: int = 1,
    tags: List[str] = None,
    top_k: int = 5,
    search_size: int = 10,
    product_segment: str = None,
) -> Dict[str, Any]:
    """Run DRBFM assist workflow with raw input and Langfuse tracking"""
    # Create workflow and config
    drbfm_assist_workflow = DrbfmAssistWorkflow(
        gemini_model_name="gemini-2.5-pro", product_segment=product_segment
    ).compile()
    config = create_langfuse_config(thread_id, tags)

    # Create initial state with raw input
    initial_state = DrbfmAssistWorkflowState(raw_input=raw_input, part=part)
    context = DrbfmWorkflowContext(top_k=top_k, search_size=search_size)

    logger.info(f"Starting DRBFM assist workflow with raw input: {raw_input[:100]}...")

    try:
        # Run workflow with Langfuse tracking
        result = drbfm_assist_workflow.invoke(
            initial_state,
            context=context,
            config=config,
        )
        return result
    except Exception as e:
        error_msg = f"invoke failed: {str(e)}"
        logger.error(f"DRBFM workflow failed for input: {raw_input[:100]}... Error: {error_msg}")
        return {
            "change_points": [],
            "per_cp_results": [{"error": error_msg}],
            "error": error_msg,
        }


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


def decompose_project_number(project_number: str) -> tuple[str, str]:
    """Decompose project number into base and suffix (e.g., 'AR-06-0013-1' -> ('AR-06-0013', '1'))"""
    pattern = re.compile(r"^(.*?)-(\d+)$")
    m = pattern.match(project_number)

    if m:
        return m.group(1), m.group(2)
    else:
        return project_number, ""


def create_output_rows(input_row: pd.Series, cp_result: Dict[str, Any], row_index: int = None) -> List[Dict[str, Any]]:
    """Create output rows for each change point result, expanding one input row into multiple output rows"""
    output_rows = []

    # Extract input data
    # Use OriginalID if it exists, otherwise use row index
    if "OriginalID" in input_row:
        original_id = input_row["OriginalID"]
    else:
        original_id = str(row_index) if row_index is not None else ""
    
    item = input_row["項目"]
    # Use "変更" column if "内容課題" doesn't exist
    raw_input = input_row["内容課題"] if "内容課題" in input_row else input_row["変更"]

    # Extract change point data
    change_point = cp_result.get("change_point", "")
    search_results = cp_result.get("relevant_search_results", [])
    estimation_results = cp_result.get("estimation_results", {})
    query_attributes = cp_result.get("change_point_attributes", None)
    search_history = cp_result.get("search_history", [])
    search_history_markdown = format_search_history_as_markdown(search_history)
    error = cp_result.get("error")
    if error:
        logger.warning(f"Error detected in change point result: {error}")

    # If no search results, create one row with empty search result fields
    if not search_results:
        output_row = {
            "OriginalID": original_id,
            "項目": item,
            "内容課題": raw_input,
            "抽出された変更点": change_point,
            "クエリ_ユニット": query_attributes.unit if query_attributes else "",
            "クエリ_部位": query_attributes.parts if query_attributes else "",
            "クエリ_変更": query_attributes.change if query_attributes else "",
            "検索履歴": search_history_markdown,
            "検索結果_ID": "",
            "AQOS_URL": "",
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
            "表題": "",
            "内容": "",
            "原因": "",
            "対策": "",
            "再発防止": "",
            "エラー詳細": cp_result.get("error", ""),
        }
        output_rows.append(output_row)
    else:
        # Create one row per search result
        for result in search_results:
            doc_id = result.get("doc_id", "")

            # Get estimation result
            if doc_id in estimation_results:
                estimation_result = estimation_results[doc_id].model_dump()
            else:
                estimation_result = {}

            project_number = result.get("project_number", "")
            # Decompose project number into base and suffix
            # Ref: https://caddijp.slack.com/archives/C094S9KFQN6/p1757389696383239
            kanri_number, fugou = decompose_project_number(project_number)
            aqos_url = (
                f"http://tadanogt116.tadano.co.jp/aqos/TR0210.aspx?KANRI_NO={kanri_number}&FUGOU={fugou}"
            )

            output_row = {
                "OriginalID": original_id,
                "項目": item,
                "内容課題": raw_input,
                "抽出された変更点": change_point,
                "クエリ_ユニット": query_attributes.unit if query_attributes else "",
                "クエリ_部位": query_attributes.parts if query_attributes else "",
                "クエリ_変更": query_attributes.change if query_attributes else "",
                "検索履歴": search_history_markdown,
                "検索結果_ID": doc_id,
                "AQOS_URL": aqos_url if project_number else "",
                "検索ステージ": result.get("search_stage", ""),
                "推定不具合_内容": estimation_result.get("potential_defect", ""),
                "推定不具合_原因": estimation_result.get("potential_cause", ""),
                "推定不具合_対策": estimation_result.get("countermeasure", ""),
                "推定不具合_根拠": format_reasoning_chains_as_markdown(
                    estimation_result.get("reasoning_chains", [])
                ),
                "検索方法": result.get("search_method", ""),
                "検索結果_型式": result.get("model_number", ""),
                "検索結果_ユニット(cause_unit)": result.get("cause", {}).get("unit", ""),
                "検索結果_部位(cause_part)": result.get("cause", {}).get("part", ""),
                "検索結果_変更(unit_part_change)": result.get("cause", {}).get("part_change", ""),
                "検索結果_故障モード(failure_mode)": result.get("failure", {}).get("mode", ""),
                "検索結果_故障影響(failure_effect)": result.get("failure", {}).get("effect", ""),
                "表題": result.get("title", ""),
                "内容": result.get("content", ""),
                "原因": result.get("cause", {}).get("original", ""),
                "対策": result.get("countermeasure", ""),
                "再発防止": result.get("recurrence_prevention", ""),
                "エラー詳細": cp_result.get("error", ""),
            }
            output_rows.append(output_row)

    return output_rows


@click.command()
@click.argument("input_path", type=Path)
@click.argument("output_path", type=Path)
@click.option(
    "--tags",
    default="drbfm_assist_workflow_evaluation",
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
    "--original-ids",
    type=str,
    help="Comma-separated list of OriginalIDs to process (if not specified, all records will be processed)",
)
@click.option(
    "--product-segment",
    type=str,
    help="Product segment to filter model numbers (e.g., 'rough_terrain_crane')",
)
def main(
    input_path: Path,
    output_path: Path,
    tags: str,
    top_k: int,
    search_size: int,
    original_ids: str,
    product_segment: str,
):
    """Generate CSV with search results for DrbfmAssistWorkflow evaluation"""
    logger.add("data/20250829_workflow_evaluation.log", level="DEBUG")

    # Convert comma-separated tags string to list
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    current_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    run_id = generate_uuid()[:8]
    tags_list = [f"{current_date}_workflow_evaluation_{run_id}"] + tags_list
    logger.info(f"Running workflow evaluation with run ID: {run_id}")

    # Read input data
    df = pd.read_csv(input_path)
    logger.info(f"Loaded {len(df)} rows from {input_path}")

    # Filter by original_ids if specified (only if OriginalID column exists)
    if original_ids and "OriginalID" in df.columns:
        original_ids_list = [id.strip() for id in original_ids.split(",") if id.strip()]
        df_filtered = df[df["OriginalID"].astype(str).isin(original_ids_list)]
        logger.info(f"Filtered to {len(df_filtered)} rows based on original_ids: {original_ids_list}")
        if len(df_filtered) == 0:
            logger.warning("No matching records found for the specified original_ids")
            return
        df = df_filtered
    elif original_ids and "OriginalID" not in df.columns:
        logger.warning("OriginalID column not found in input CSV. Ignoring --original-ids filter.")

    all_output_rows = []

    for idx, row in df.iterrows():
        raw_input = row["変更"]
        part = row["項目"]

        logger.info(f"Processing row {idx + 1}/{len(df)}: {raw_input[:50]}...")

        # Run DRBFM assist workflow with raw input and Langfuse tracking
        original_id_tag = f"OriginalID:{row.get('OriginalID', idx)}" if "OriginalID" in row else f"RowIndex:{idx}"
        result = run_drbfm_assist_workflow(
            raw_input=raw_input,
            part=part,
            thread_id=idx,
            tags=tags_list + [original_id_tag],
            top_k=top_k,
            search_size=search_size,
            product_segment=product_segment,
        )

        # Extract results
        change_points = result.get("change_points", [])
        per_cp_results = result.get("per_cp_results", [])

        logger.info(f"Extracted {len(change_points)} change points")
        logger.info(f"Processed {len(per_cp_results)} change point results")

        # Process each change point result
        if not per_cp_results:
            # If no results, create a single row with empty values
            empty_result = {
                "change_point": "",
                "relevant_search_results": [],
                "estimation_results": {},
                "error": "No change points extracted",
            }
            output_rows = create_output_rows(row, empty_result, row_index=idx)
            all_output_rows.extend(output_rows)
        else:
            for cp_result in per_cp_results:
                output_rows = create_output_rows(row, cp_result, row_index=idx)
                all_output_rows.extend(output_rows)
                logger.info(
                    f"Generated {len(output_rows)} output rows for change point: {cp_result.get('change_point', 'Unknown')}"  # noqa: E501
                )

    # Create output DataFrame
    output_df = pd.DataFrame(all_output_rows)

    # Save to CSV
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    logger.info(f"Evaluation results saved to {output_path}")
    logger.info(f"Total output rows: {len(output_df)}")

    # Summary statistics
    total_inputs = len(df)
    total_change_points = output_df["抽出された変更点"].nunique()
    total_search_results = len(output_df[output_df["検索結果_ID"] != ""])

    logger.info("\n=== Summary ===")
    logger.info(f"Total inputs: {total_inputs}")
    logger.info(f"Total unique change points: {total_change_points}")
    logger.info(f"Total search results: {total_search_results}")


if __name__ == "__main__":
    main()
