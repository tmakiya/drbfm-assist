"""Extract attributes from failure document images using Google Gemini AI.

This module processes PNG image files from a specified directory and extracts
attributes (部位, 故障モード, 機能) using Google Gemini AI model via Vertex AI.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import pandas as pd
from dotenv import load_dotenv
from google.genai.types import Part
from langfuse import Langfuse
from loguru import logger

from drassist.llm.gemini_client import GeminiClient

load_dotenv()

MODEL = "gemini-2.5-pro"

# Gemini API pricing (USD per 1,000,000 tokens)
GEMINI_PRICES = {
    "input_le_200k": Decimal("1.25"),
    "input_gt_200k": Decimal("2.50"),
    "output_le_200k": Decimal("10.00"),
    "output_gt_200k": Decimal("15.00"),
}

# Exchange rate
USD_TO_JPY = Decimal("155.59")


def calculate_cost_jpy(input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate cost in JPY for given token usage.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens (including thinking tokens)

    Returns:
        Cost in JPY

    """
    M = Decimal(1_000_000)

    def per_mtok(rate: Decimal, tokens: int) -> Decimal:
        return (rate * Decimal(tokens)) / M

    # Determine pricing tier based on input tokens
    input_rate = GEMINI_PRICES["input_le_200k"] if input_tokens <= 200_000 else GEMINI_PRICES["input_gt_200k"]
    output_rate = (
        GEMINI_PRICES["output_le_200k"] if input_tokens <= 200_000 else GEMINI_PRICES["output_gt_200k"]
    )

    input_cost_usd = per_mtok(input_rate, input_tokens)
    output_cost_usd = per_mtok(output_rate, output_tokens)

    total_cost_usd = input_cost_usd + output_cost_usd
    total_cost_jpy = (total_cost_usd * USD_TO_JPY).quantize(Decimal("0.01"))

    return total_cost_jpy


def mk_client(model: str = MODEL) -> GeminiClient:
    """Create and return a Gemini client using Vertex AI mode."""
    return GeminiClient(model_name=model)


def fetch_langfuse_prompt() -> tuple[str, Dict[str, Any]]:
    """Fetch prompt and response schema from Langfuse.

    Returns:
        Tuple of (system_instruction, response_schema)

    """
    logger.info("Fetching prompt from Langfuse...")
    langfuse = Langfuse()
    langfuse_prompt = langfuse.get_prompt("extract_attributes_from_failure_docs", label="1d84c619")
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    logger.info("Prompt retrieved from Langfuse")
    logger.debug(f"Response schema: {response_schema}")

    return system_instruction, response_schema


def process_single_image(
    png_path: Path,
    client: GeminiClient,
    system_instruction: str,
    response_schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Process a single PNG image and return extracted attributes.

    Args:
        png_path: Path to the PNG file
        client: GeminiClient instance
        system_instruction: System instruction for the model
        response_schema: JSON schema for structured output

    Returns:
        Dictionary containing extracted data and metadata

    """
    drawing_id = png_path.stem  # Filename without extension
    logger.info(f"Processing image: {drawing_id}")

    # Check file size (50MB limit)
    MAX_SIZE = 50 * 1024 * 1024  # 50MB in bytes
    file_size = png_path.stat().st_size

    default_result = {
        "drawing_id": drawing_id,
        "部位": "",
        "故障モード": "",
        "機能": "",
        "Cost": Decimal("0.00"),
        "status": "",
        "error": "",
    }

    if file_size > MAX_SIZE:
        logger.warning(f"Image {drawing_id} size ({file_size} bytes) exceeds 50MB limit. Skipping.")
        default_result["status"] = "skipped_large_file"
        default_result["error"] = f"File size {file_size} bytes exceeds 50MB limit"
        return default_result

    try:
        # Read PNG file as bytes
        png_bytes = png_path.read_bytes()

        # Prepare content with PNG image
        contents = [
            Part.from_text(text="Input:"),
            Part.from_bytes(data=png_bytes, mime_type="image/png"),
        ]

        # Generate content with system instruction
        extra_config = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }

        response = client._generate_content(
            contents,
            extra_config,
            system_instruction=system_instruction,
        )

        # Parse JSON result
        result = json.loads(response.text)

        # Get token usage from response metadata
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0)
        output_tokens = getattr(usage, "candidates_token_count", 0)
        thought_tokens = getattr(usage, "thoughts_token_count", 0)
        output_tokens += thought_tokens  # Include thinking tokens

        # Calculate cost in JPY
        cost_jpy = calculate_cost_jpy(input_tokens, output_tokens)

        logger.info(f"Successfully processed {drawing_id}")
        logger.info(
            f"Tokens: {input_tokens:,} input, {output_tokens:,} output | Cost: ¥{cost_jpy:.2f}"
        )

        return {
            "drawing_id": drawing_id,
            "部位": result.get("部位", ""),
            "故障モード": result.get("故障モード", ""),
            "機能": result.get("機能", ""),
            "Cost": cost_jpy,
            "status": "success",
            "error": "",
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for {drawing_id}: {e}")
        default_result["status"] = "error"
        default_result["error"] = f"JSON parse error: {str(e)}"
        return default_result

    except Exception as e:
        logger.error(f"Failed to process {drawing_id}: {e}")
        default_result["status"] = "error"
        default_result["error"] = str(e)
        return default_result


def collect_png_files(input_dir: Path, filter_drawing_ids: Optional[List[str]] = None) -> List[Path]:
    """Collect PNG files from input directory, optionally filtered by drawing_ids.

    Args:
        input_dir: Directory containing PNG files
        filter_drawing_ids: Optional list of drawing_ids to filter by

    Returns:
        List of PNG file paths

    """
    all_png_files = sorted(input_dir.glob("*.png"))

    if filter_drawing_ids is None:
        return all_png_files

    # Filter by drawing_ids
    filter_set = set(filter_drawing_ids)
    filtered_files = [f for f in all_png_files if f.stem in filter_set]

    logger.info(f"Filtered {len(all_png_files)} files to {len(filtered_files)} files")
    return filtered_files


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_csv", type=click.Path(path_type=Path))
@click.option(
    "--filter-csv",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    default=None,
    help="CSV file containing drawing_id column to filter images",
)
@click.option("--max-workers", default=4, type=int, help="Maximum number of parallel workers")
@click.option("--model", default=MODEL, help="Gemini model name")
def main(
    input_dir: Path,
    output_csv: Path,
    filter_csv: Optional[Path],
    max_workers: int,
    model: str,
) -> None:
    """Extract attributes from PNG images and save to CSV.

    Args:
        input_dir: Directory containing PNG files
        output_csv: Output CSV file path
        filter_csv: Optional CSV file with drawing_id column to filter images
        max_workers: Maximum number of parallel workers (default: 4)
        model: Gemini model name (default: gemini-2.5-pro)

    """
    logger.info(f"Starting attribute extraction from PNG files in: {input_dir}")

    # Load filter drawing_ids if provided
    filter_drawing_ids = None
    if filter_csv:
        logger.info(f"Loading filter drawing_ids from: {filter_csv}")
        filter_df = pd.read_csv(filter_csv)
        if "drawing_id" not in filter_df.columns:
            logger.error("Filter CSV must contain 'drawing_id' column")
            return
        filter_drawing_ids = filter_df["drawing_id"].tolist()
        logger.info(f"Loaded {len(filter_drawing_ids)} drawing_ids for filtering")

    # Collect PNG files
    png_files = collect_png_files(input_dir, filter_drawing_ids)

    if not png_files:
        logger.warning(f"No PNG files found in {input_dir}")
        return

    logger.info(f"Found {len(png_files)} PNG files to process")

    # Fetch prompt and schema from Langfuse
    system_instruction, response_schema = fetch_langfuse_prompt()

    # Create shared Gemini client
    client = mk_client(model)
    logger.info(f"Created Gemini client with model: {model}")

    # Process images in parallel
    logger.info(f"Processing {len(png_files)} images with {max_workers} parallel workers")
    results = []

    # Create partial function with pre-bound arguments
    process_with_client = partial(
        process_single_image,
        client=client,
        system_instruction=system_instruction,
        response_schema=response_schema,
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_path = {executor.submit(process_with_client, path): path for path in png_files}

        # Collect results as they complete
        for i, future in enumerate(as_completed(future_to_path), 1):
            path = future_to_path[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"Progress: {i}/{len(png_files)} images completed ({path.stem})")
            except Exception as e:
                logger.error(f"Failed to process {path.stem}: {e}")
                results.append({
                    "drawing_id": path.stem,
                    "部位": "",
                    "故障モード": "",
                    "機能": "",
                    "Cost": Decimal("0.00"),
                    "status": "error",
                    "error": str(e),
                })

    # Save results to CSV
    if results:
        # Prepare DataFrame with required columns only
        df_results = pd.DataFrame(results)

        # Select only the required columns for output
        output_columns = ["drawing_id", "部位", "故障モード", "機能", "Cost"]
        df_output = df_results[output_columns].copy()

        # Convert Decimal to float for CSV output
        df_output["Cost"] = df_output["Cost"].astype(float)

        # Ensure output directory exists
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        # Save to CSV
        df_output.to_csv(output_csv, index=False)
        logger.info(f"Results saved to: {output_csv}")
        logger.info(f"Processed {len(results)} images total")

        # Summary statistics
        success_count = sum(1 for r in results if r["status"] == "success")
        skipped_count = sum(1 for r in results if r["status"] == "skipped_large_file")
        error_count = sum(1 for r in results if r["status"] == "error")

        # Cost statistics
        total_cost_jpy = sum(r.get("Cost", Decimal("0.00")) for r in results)

        logger.info(
            f"Summary: {success_count} successful, {skipped_count} skipped (too large), {error_count} errors"
        )

        # Print total cost to stdout
        print(f"\n{'='*50}")
        print(f"Total Cost: ¥{total_cost_jpy:.2f} JPY")
        print(f"{'='*50}\n")

    else:
        logger.warning("No results to save")


if __name__ == "__main__":
    main()
