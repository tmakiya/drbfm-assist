"""PDF files to structured DRBFM data extraction using Google Gemini AI.

This module processes PDF files from a specified directory and extracts DRBFM (Design Review Based on Failure Mode)
structured data using Google Gemini AI model via Vertex AI.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import pandas as pd
from dotenv import load_dotenv
from google.genai.types import Part
from langfuse import Langfuse
from loguru import logger

from drassist.llm.gemini_client import GeminiClient

load_dotenv()

MODEL = "gemini-2.5-pro"
DEFAULT_MAX_WORKERS = 5

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


def mk_client(model: str = MODEL) -> GeminiClient:
    """Create and return a Gemini client using Vertex AI mode."""
    return GeminiClient(model_name=model)


def fetch_langfuse_prompt(prompt_name: str) -> str:
    """Fetch prompt from Langfuse.

    Args:
        prompt_name: Name of the prompt to fetch

    Returns:
        Compiled system instruction string

    """
    logger.info(f"Fetching prompt '{prompt_name}' from Langfuse...")
    langfuse = Langfuse()
    langfuse_prompt = langfuse.get_prompt(prompt_name)
    system_instruction = langfuse_prompt.compile()
    logger.info(f"Prompt '{prompt_name}' retrieved from Langfuse")
    return system_instruction


def load_file_id_mapping(mapping_csv: Optional[Path]) -> Dict[str, str]:
    """Load file stem to original_file_id mapping from CSV.

    Args:
        mapping_csv: Path to the mapping CSV file

    Returns:
        Dictionary mapping file_stem to original_file_id

    """
    if mapping_csv is None:
        return {}

    if not mapping_csv.exists():
        logger.warning(f"Mapping CSV not found: {mapping_csv}")
        return {}

    df = pd.read_csv(mapping_csv)
    mapping = dict(zip(df["file_stem"], df["original_file_id"]))
    logger.info(f"Loaded {len(mapping)} file ID mappings from {mapping_csv}")
    return mapping


def map_part_to_section_and_function(
    record: Dict[str, Any],
    client: GeminiClient,
    system_instruction: str,
) -> Dict[str, str]:
    """Map part, change_point, and function to section and function_category.

    Args:
        record: Record containing part, change_point, and function
        client: GeminiClient instance
        system_instruction: System instruction for the mapping prompt

    Returns:
        Dictionary with section and function_category

    """
    input_data = {
        "input_part": record.get("part", ""),
        "input_part_change": record.get("change_point", ""),
        "input_function": record.get("function", ""),
    }

    try:
        contents = [
            Part.from_text(text=json.dumps(input_data, ensure_ascii=False)),
        ]

        extra_config = {
            "response_mime_type": "application/json",
        }

        response = client._generate_content(
            contents,
            extra_config,
            system_instruction=system_instruction,
        )

        result = json.loads(response.text)

        return {
            "section": result.get("section", ""),
            "function_category": result.get("function", ""),
        }

    except Exception as e:
        logger.error(f"Failed to map part to section: {e}")
        return {
            "section": "",
            "function_category": "",
        }


def process_single_record(
    record_info: Tuple[int, Dict[str, Any], str, str, str],
    client: GeminiClient,
    mapping_prompt: str,
) -> Dict[str, Any]:
    """Process a single record with mapping.

    Args:
        record_info: Tuple of (index, record, source_file, product, original_file_id)
        client: GeminiClient instance
        mapping_prompt: System instruction for mapping

    Returns:
        Flattened record with all fields

    """
    idx, record, source_file, product, original_file_id = record_info

    # Convert cause array to JSON string
    cause_value = record.get("cause", [])
    if isinstance(cause_value, list):
        cause_str = json.dumps(cause_value, ensure_ascii=False)
    else:
        cause_str = cause_value  # Fallback for string type

    # Map part to section and function_category
    mapping_result = map_part_to_section_and_function(record, client, mapping_prompt)

    flat_record = {
        "_index": idx,  # Keep track of original order
        "source_file": source_file,
        "original_file_id": original_file_id,
        "product": product,
        "part": record.get("part", ""),
        "change_point": record.get("change_point", ""),
        "function": record.get("function", ""),
        "section": mapping_result["section"],
        "function_category": mapping_result["function_category"],
        "failure_mode": record.get("failure_mode", ""),
        "cause": cause_str,
        "effect": record.get("effect", ""),
        "countermeasure": record.get("countermeasure", ""),
    }

    return flat_record


def process_pdf_file(
    pdf_path: Path,
    client: GeminiClient,
    system_instruction: str,
) -> Dict[str, Any]:
    """Process a single PDF file and return extracted DRBFM data.

    Args:
        pdf_path: Path to the PDF file
        client: GeminiClient instance
        system_instruction: System instruction for the model

    Returns:
        Dictionary containing extracted data and metadata

    """
    logger.info(f"Processing PDF: {pdf_path.name}")

    # Check file size (50MB limit)
    MAX_SIZE = 50 * 1024 * 1024  # 50MB in bytes
    file_size = pdf_path.stat().st_size

    default_result = {
        "source_file": pdf_path.name,
        "status": "",
        "file_size": file_size,
        "error": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "product": "",
        "records": [],
    }

    if file_size > MAX_SIZE:
        logger.warning(f"PDF {pdf_path.name} size ({file_size} bytes) exceeds 50MB limit. Skipping.")
        default_result["status"] = "skipped_large_file"
        default_result["error"] = f"File size {file_size} bytes exceeds 50MB limit"
        return default_result

    try:
        # Read PDF file as bytes
        pdf_bytes = pdf_path.read_bytes()

        # Prepare content with PDF
        contents = [
            Part.from_text(text="Input:"),
            Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        ]

        # Generate content with system instruction
        extra_config = {
            "response_mime_type": "application/json",
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
        output_tokens += thought_tokens

        # Calculate cost
        cost = calculate_cost(client.model_name, input_tokens, output_tokens)

        logger.info(f"Successfully processed {pdf_path.name}")
        logger.info(f"Tokens: {input_tokens:,} input, {output_tokens:,} output | Cost: ${cost:.4f}")
        logger.info(f"Extracted {len(result.get('records', []))} records")

        return {
            "source_file": pdf_path.name,
            "status": "success",
            "file_size": file_size,
            "error": "",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": float(cost),
            "product": result.get("product", ""),
            "records": result.get("records", []),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for {pdf_path.name}: {e}")
        default_result["status"] = "error"
        default_result["error"] = f"JSON parse error: {str(e)}"
        return default_result

    except Exception as e:
        logger.error(f"Failed to process {pdf_path.name}: {e}")
        default_result["status"] = "error"
        default_result["error"] = str(e)
        return default_result


def flatten_records(
    results: List[Dict[str, Any]],
    client: GeminiClient,
    mapping_prompt: str,
    file_id_mapping: Dict[str, str],
    max_workers: int,
) -> List[Dict[str, Any]]:
    """Flatten nested records from all PDF results into a single list with parallel processing.

    Args:
        results: List of processing results from each PDF
        client: GeminiClient instance for mapping
        mapping_prompt: System instruction for part-to-section mapping
        file_id_mapping: Dictionary mapping file_stem to original_file_id
        max_workers: Maximum number of parallel workers

    Returns:
        Flattened list of records with source file and product info

    """
    # Prepare all records with their metadata
    record_infos: List[Tuple[int, Dict[str, Any], str, str, str]] = []
    idx = 0

    for result in results:
        if result["status"] != "success":
            continue

        source_file = result["source_file"]
        product = result["product"]

        # Get original_file_id from mapping
        file_stem = Path(source_file).stem
        original_file_id = file_id_mapping.get(file_stem, "")

        for record in result["records"]:
            record_infos.append((idx, record, source_file, product, original_file_id))
            idx += 1

    total_records = len(record_infos)
    logger.info(f"Processing {total_records} records with {max_workers} parallel workers...")

    # Create partial function with pre-bound client and mapping_prompt
    process_func = partial(process_single_record, client=client, mapping_prompt=mapping_prompt)

    # Process records in parallel
    flattened = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_record = {executor.submit(process_func, record_info): record_info for record_info in record_infos}

        for future in as_completed(future_to_record):
            completed += 1
            try:
                flat_record = future.result()
                flattened.append(flat_record)
                if completed % 10 == 0 or completed == total_records:
                    logger.info(f"Mapping progress: {completed}/{total_records} records completed")
            except Exception as e:
                record_info = future_to_record[future]
                logger.error(f"Failed to process record {record_info[0]}: {e}")

    # Sort by original index to maintain order
    flattened.sort(key=lambda x: x.pop("_index"))

    return flattened


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_csv", type=click.Path(path_type=Path))
@click.option("--mapping-csv", type=click.Path(exists=True, path_type=Path), help="CSV file mapping file_stem to original_file_id")
@click.option("--model", default=MODEL, help="Gemini model name")
@click.option("--max-workers", default=DEFAULT_MAX_WORKERS, type=int, help="Maximum number of parallel workers for mapping")
def main(input_dir: Path, output_csv: Path, mapping_csv: Optional[Path], model: str, max_workers: int) -> None:
    """Process PDF files from a directory and extract DRBFM data to CSV.

    Args:
        input_dir: Directory containing PDF files
        output_csv: Output CSV file path
        mapping_csv: CSV file mapping file_stem to original_file_id
        model: Gemini model name (default: gemini-2.5-pro)
        max_workers: Maximum number of parallel workers for mapping

    """
    logger.info(f"Starting DRBFM extraction from PDF files in: {input_dir}")

    # Find all PDF files in the directory
    pdf_files = sorted(input_dir.glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return

    logger.info(f"Found {len(pdf_files)} PDF files")

    # Load file ID mapping
    file_id_mapping = load_file_id_mapping(mapping_csv)

    # Fetch prompts from Langfuse
    structuring_prompt = fetch_langfuse_prompt("structuring_drbfm_from_img")
    mapping_prompt = fetch_langfuse_prompt("map_part_to_section_and_function")

    # Create Gemini client
    client = mk_client(model)
    logger.info(f"Created Gemini client with model: {model}")

    # Process each PDF file
    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        logger.info(f"Processing file {i}/{len(pdf_files)}: {pdf_path.name}")
        result = process_pdf_file(pdf_path, client, structuring_prompt)
        results.append(result)

    # Flatten records and create DataFrame with parallel processing
    logger.info("Mapping records to sections and function categories...")
    flattened_records = flatten_records(results, client, mapping_prompt, file_id_mapping, max_workers)

    if flattened_records:
        df = pd.DataFrame(flattened_records)

        # Ensure output directory exists
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        # Save to CSV
        df.to_csv(output_csv, index=False)
        logger.info(f"Results saved to: {output_csv}")
        logger.info(f"Total records extracted: {len(flattened_records)}")
    else:
        logger.warning("No records extracted from any PDF files")

    # Summary statistics
    success_count = sum(1 for r in results if r["status"] == "success")
    skipped_count = sum(1 for r in results if r["status"] == "skipped_large_file")
    error_count = sum(1 for r in results if r["status"] == "error")

    total_cost = sum(r.get("cost", 0.0) for r in results)
    total_input_tokens = sum(r.get("input_tokens", 0) for r in results)
    total_output_tokens = sum(r.get("output_tokens", 0) for r in results)

    logger.info(f"Summary: {success_count} successful, {skipped_count} skipped, {error_count} errors")
    logger.info(f"Token usage: {total_input_tokens:,} input, {total_output_tokens:,} output")
    logger.info(f"Total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
