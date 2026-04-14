"""PNG images to structured DRBFM data extraction using Google Gemini AI.

This module processes PNG image files grouped by original_id and extracts DRBFM (Design Review Based on Failure Mode)
structured data using Google Gemini AI model via Vertex AI.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Dict, List

import click
import pandas as pd
from dotenv import load_dotenv
from google.genai.types import Part
from langfuse import Langfuse
from loguru import logger

from drassist.config import ConfigManager
from drassist.llm.gemini_client import GeminiClient

load_dotenv()  # Load environment variables from .env file

MODEL = "gemini-2.5-pro"  # or gemini-2.5-pro

# List of mandatory original_ids for test mode
MANDATORY_TEST_IDS = [
    "8e758f51-68e1-4f27-9114-b46cdd0cdf7e",
    "ee7abf0e-7aa3-4f0c-b958-3e262b42ff74",
    "f73a1e57-6c31-4c43-87c8-ad9969d4e7b0",
    "966c704f-8f0e-4ed1-a457-4fa0cea545d2",
    "bdc0e3e4-9b84-4697-915b-80cb71838a74",
]

# Gemini API pricing (USD per 1,000,000 tokens)
GEMINI_PRICES = {
    "gemini-2.5-pro": {
        "input_le_200k": Decimal("1.25"),
        "input_gt_200k": Decimal("2.50"),
        "output_le_200k": Decimal("10.00"),
        "output_gt_200k": Decimal("15.00"),
    },
    "gemini-2.5-flash": {
        "input": Decimal("0.30"),
        "output": Decimal("2.50"),
    },
    "gemini-2.5-flash-lite": {
        "input": Decimal("0.10"),
        "output": Decimal("0.40"),
    },
}


@dataclass
class CostBreakdown:
    """Cost breakdown for API usage."""

    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate cost in USD for given token usage."""
    if model_id not in GEMINI_PRICES:
        logger.warning(f"Unknown model {model_id}, defaulting to gemini-2.5-flash pricing")
        model_id = "gemini-2.5-flash"

    prices = GEMINI_PRICES[model_id]
    M = Decimal(1_000_000)

    def per_mtok(rate: Decimal, tokens: int) -> Decimal:
        return (rate * Decimal(tokens)) / M

    # Calculate input cost (Pro model has tiered pricing)
    if model_id == "gemini-2.5-pro":
        input_rate = prices["input_le_200k"] if input_tokens <= 200_000 else prices["input_gt_200k"]
        output_rate = prices["output_le_200k"] if output_tokens <= 200_000 else prices["output_gt_200k"]
    else:
        input_rate = prices["input"]
        output_rate = prices["output"]

    input_cost = per_mtok(input_rate, input_tokens)
    output_cost = per_mtok(output_rate, output_tokens)

    total_cost = (input_cost + output_cost).quantize(Decimal("0.0001"))
    return total_cost




def mk_client(model: str = MODEL):
    """Create and return a Gemini client using Vertex AI mode."""
    return GeminiClient(model_name=model)


def load_unit_list():
    """Load standardized unit list from config file."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_path = project_root / "configs" / "8d8232f3.yaml"
    config = ConfigManager(str(config_path))
    return config.get("unit_list", [])


def fetch_langfuse_prompt():
    """Fetch prompt and response schema from Langfuse."""
    logger.info("Fetching prompt from Langfuse...")
    langfuse = Langfuse()
    langfuse_prompt = langfuse.get_prompt("extract_attributes_from_failure_docs")
    response_schema = langfuse_prompt.config["response_schema"]
    
    # Load unit list from config and prepare for prompt
    unit_list = load_unit_list()
    unit_list_str = "\n".join(f"- {unit}" for unit in unit_list)
    system_instruction = langfuse_prompt.compile(unit_list=unit_list_str)
    
    logger.info("Prompt retrieved from Langfuse")
    logger.debug(f"Response schema: {response_schema}")
    
    return system_instruction, response_schema


def get_default_value_for_type(field_type, field_config=None):
    """Get default value based on field type from schema."""
    if field_type == "array":
        return []
    elif field_type == "number":
        return 0
    elif field_type == "boolean":
        return False
    else:  # string or any other type
        return ""


def call_once_multi_images(png_bytes_list: List[bytes], client: GeminiClient, system_instruction: str, response_schema: dict):
    """Call Gemini AI once with multiple PNG images and return parsed JSON result with cost info."""
    # Prepare content with multiple PNG images only (PROMPT moved to system instruction)
    contents = []
    # テキストプロンプトを最初に追加
    contents.append(Part.from_text(text="Input:"))
    for png_bytes in png_bytes_list:
        contents.append(Part.from_bytes(data=png_bytes, mime_type="image/png"))

    # Use GeminiClient's internal method to generate content with PNG images and system instruction
    extra_config = {
        "response_mime_type": "application/json",
        "response_schema": response_schema,
    }

    response = client._generate_content(contents, extra_config, system_instruction=system_instruction)

    # Parse JSON result
    result = json.loads(response.text)

    # Get token usage from response metadata
    usage = response.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", 0)
    output_tokens = getattr(usage, "candidates_token_count", 0)
    thought_tokens = getattr(usage, "thoughts_token_count", 0)

    output_tokens += thought_tokens  # Include thought tokens in output

    # Calculate cost using client's model name
    cost = calculate_cost(client.model_name, input_tokens, output_tokens)

    # Add cost breakdown to result
    result["_cost_info"] = {"input_tokens": input_tokens, "output_tokens": output_tokens, "cost": float(cost)}

    return result


def process_dataframe(df: pd.DataFrame, png_dir: Path) -> List[Dict]:
    """Process dataframe and return groups of PNG files by original_id."""
    groups = []

    # Group by original_id and sort by page_number
    for original_id, group_df in df.groupby("original_id"):
        group_df = group_df.sort_values("page_number")

        png_paths = []
        drawing_ids = []

        for _, row in group_df.iterrows():
            drawing_id = row["drawing_id"]
            png_path = png_dir / f"{drawing_id}.png"

            if png_path.exists():
                png_paths.append(png_path)
                drawing_ids.append(drawing_id)
            else:
                logger.warning(f"PNG file not found: {png_path}")

        if png_paths:
            groups.append(
                {
                    "original_id": original_id,
                    "png_paths": png_paths,
                    "drawing_ids": drawing_ids,
                    "page_count": len(png_paths),
                }
            )

    logger.info(f"Found {len(groups)} original_id groups with PNG files")
    return groups


def process_single_original_group(group: Dict, client: GeminiClient, system_instruction: str, response_schema: dict) -> dict:
    """Process a single original_id group of PNG files and return analysis result."""
    original_id = group["original_id"]
    png_paths = group["png_paths"]
    drawing_ids = group["drawing_ids"]

    logger.info(f"Processing original_id: {original_id} ({len(png_paths)} PNG files)")

    # Check total file size (50MB limit)
    MAX_SIZE = 50 * 1024 * 1024  # 50MB in bytes
    total_size = sum(path.stat().st_size for path in png_paths)

    # Create default result with dynamic schema fields
    default_result = {
        "original_id": original_id,
        "drawing_ids": drawing_ids,
        "status": "",
        "total_file_size": total_size,
        "page_count": len(png_paths),
        "error": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
    }
    
    # Add default values for all schema properties dynamically
    if "properties" in response_schema:
        for field_name, field_config in response_schema["properties"].items():
            field_type = field_config.get("type", "string")
            default_result[field_name] = get_default_value_for_type(field_type, field_config)

    if total_size > MAX_SIZE:
        logger.warning(
            f"Original ID {original_id} total size ({total_size} bytes) exceeds 50MB limit. Skipping."
        )
        default_result["status"] = "skipped_large_file"
        default_result["error"] = f"Total file size {total_size} bytes exceeds 50MB limit"
        return default_result

    try:
        # Read all PNG files as bytes
        png_bytes_list = []
        for png_path in png_paths:
            png_bytes_list.append(png_path.read_bytes())

        # Call Gemini AI to analyze the PNG images
        result = call_once_multi_images(png_bytes_list, client, system_instruction, response_schema)

        # Extract cost information
        cost_info = result.pop("_cost_info", {})
        input_tokens = cost_info.get("input_tokens", 0)
        output_tokens = cost_info.get("output_tokens", 0)
        cost = cost_info.get("cost", 0.0)

        # Add metadata and cost information
        result.update(
            {
                "original_id": original_id,
                "drawing_ids": drawing_ids,
                "status": "success",
                "total_file_size": total_size,
                "page_count": len(png_paths),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            }
        )

        # Log cost information
        logger.info(f"Successfully processed original_id {original_id}")
        logger.info(f"Tokens: {input_tokens:,} input, {output_tokens:,} output | Cost: ${cost:.4f}")

        return result

    except Exception as e:
        logger.error(f"Failed to process original_id {original_id}: {e}")
        default_result["status"] = "error"
        default_result["error"] = str(e)
        return default_result


@click.command()
@click.argument("input_csv", type=click.Path(exists=True, file_okay=True, path_type=Path))
@click.argument("png_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_csv", type=click.Path(path_type=Path))
@click.option("--model", default=MODEL, help="Gemini model name")
@click.option("--max-workers", default=3, type=int, help="Maximum number of parallel workers")
@click.option("--test", type=int, help="Test mode: randomly sample N original_ids to process")
def main(input_csv: Path, png_dir: Path, output_csv: Path, model: str, max_workers: int, test: int) -> None:
    """Process PNG files grouped by original_id and extract DRBFM data to CSV.

    Args:
        input_csv: CSV file containing original_id, drawing_id, page_number columns
        png_dir: Directory containing PNG files (named as {drawing_id}.png)
        output_csv: Output CSV file path
        model: Gemini model name (default: gemini-2.5-flash)
        max_workers: Maximum number of parallel workers (default: 3)
        test: Test mode - randomly sample N original_ids to process

    """
    logger.info(f"Starting DRBFM analysis on PNG files from dataframe: {input_csv}")
    
    if test:
        logger.info(f"Running in TEST MODE - will randomly sample {test} original_ids")

    # Load dataframe
    df = pd.read_csv(input_csv)
    required_columns = ["original_id", "drawing_id", "page_number"]

    for col in required_columns:
        if col not in df.columns:
            logger.error(f"Required column '{col}' not found in CSV file")
            return

    # Process dataframe to get groups
    groups = process_dataframe(df, png_dir)

    if not groups:
        logger.warning("No PNG file groups found")
        return

    # Test mode: randomly sample specified number of original_ids, ensuring mandatory IDs are included
    if test:
        import random
        random.seed(42)  # Set seed for reproducibility

        mandatory_groups = [g for g in groups if g["original_id"] in MANDATORY_TEST_IDS]
        other_groups = [g for g in groups if g["original_id"] not in MANDATORY_TEST_IDS]

        num_mandatory = len(mandatory_groups)
        num_to_sample = max(0, test - num_mandatory)
        
        sampled_groups = []
        if num_to_sample > 0 and other_groups:
            sample_size = min(num_to_sample, len(other_groups))
            sampled_groups = random.sample(other_groups, sample_size)

        groups = mandatory_groups + sampled_groups
        
        logger.info(f"Test mode: Selected {len(groups)} original_id groups for processing")
        logger.info(f"({num_mandatory} mandatory, {len(sampled_groups)} random)")

    # Fetch prompt and schema from Langfuse
    system_instruction, response_schema = fetch_langfuse_prompt()

    # Create shared Gemini client for all workers
    client = mk_client(model)
    logger.info(f"Created shared Gemini client with model: {model}")

    # Process groups in parallel using functools.partial
    logger.info(f"Processing {len(groups)} original_id groups with {max_workers} parallel workers")
    results = []

    # Create partial function with pre-bound client, system_instruction, and response_schema
    process_with_client = partial(
        process_single_original_group, 
        client=client,
        system_instruction=system_instruction,
        response_schema=response_schema
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks using the partial function
        future_to_group = {executor.submit(process_with_client, group): group for group in groups}

        # Collect results as they complete
        for i, future in enumerate(as_completed(future_to_group), 1):
            group = future_to_group[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(
                    f"Progress: {i}/{len(groups)} groups completed (original_id: {group['original_id']})"
                )
            except Exception as e:
                logger.error(f"Failed to process original_id {group['original_id']}: {e}")
                # Create error result with dynamic schema fields
                error_result = {
                    "original_id": group["original_id"],
                    "drawing_ids": group["drawing_ids"],
                    "status": "error",
                    "total_file_size": 0,
                    "page_count": group["page_count"],
                    "error": str(e),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0.0,
                }
                
                # Add default values for all schema properties dynamically
                if "properties" in response_schema:
                    for field_name, field_config in response_schema["properties"].items():
                        field_type = field_config.get("type", "string")
                        error_result[field_name] = get_default_value_for_type(field_type, field_config)
                
                results.append(error_result)

    # Save results to CSV
    if results:
        df_results = pd.DataFrame(results)

        # Ensure output directory exists
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        # Save to CSV
        df_results.to_csv(output_csv, index=False)
        logger.info(f"Results saved to: {output_csv}")
        logger.info(f"Processed {len(results)} original_id groups total")

        # Summary statistics
        success_count = sum(1 for r in results if r["status"] == "success")
        skipped_count = sum(1 for r in results if r["status"] == "skipped_large_file")
        error_count = sum(1 for r in results if r["status"] == "error")

        # Cost statistics
        total_cost = sum(r.get("cost", 0.0) for r in results)
        total_input_tokens = sum(r.get("input_tokens", 0) for r in results)
        total_output_tokens = sum(r.get("output_tokens", 0) for r in results)
        successful_cost = sum(r.get("cost", 0.0) for r in results if r["status"] == "success")

        logger.info(
            f"Summary: {success_count} successful, {skipped_count} skipped (too large), {error_count} errors"
        )
        logger.info(f"Token usage: {total_input_tokens:,} input, {total_output_tokens:,} output")
        logger.info(f"Total cost: ${total_cost:.4f} (successful files: ${successful_cost:.4f})")

        if success_count > 0:
            avg_cost = successful_cost / success_count
            logger.info(f"Average cost per successful group: ${avg_cost:.4f}")
    else:
        logger.warning("No results to save")


if __name__ == "__main__":
    main()
