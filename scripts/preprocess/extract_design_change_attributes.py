"""Extract attributes from design change PDFs using Google Gemini AI.

This module processes PDF files from a specified directory and extracts
attributes (product, section, function, failure_mode) using Google Gemini AI model via Vertex AI.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path
from typing import Any, Dict, List

import click
import pandas as pd
from dotenv import load_dotenv
from google.genai.types import Part
from langfuse import Langfuse
from loguru import logger

from drassist.llm.gemini_client import GeminiClient

load_dotenv()

MODEL = "gemini-2.5-pro"


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
    langfuse_prompt = langfuse.get_prompt("extract_attributes_from_design_changes")
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    logger.info("Prompt retrieved from Langfuse")
    logger.debug(f"Response schema: {response_schema}")

    return system_instruction, response_schema


def process_single_pdf(
    pdf_path: Path,
    client: GeminiClient,
    system_instruction: str,
    response_schema: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Process a single PDF file and return extracted attributes.

    Args:
        pdf_path: Path to the PDF file
        client: GeminiClient instance
        system_instruction: System instruction for the model
        response_schema: JSON schema for structured output

    Returns:
        List of dictionaries containing extracted data and metadata

    """
    original_file_id = pdf_path.stem  # Filename without extension
    logger.info(f"Processing PDF: {original_file_id}")

    # Check file size (50MB limit for Gemini)
    MAX_SIZE = 50 * 1024 * 1024  # 50MB in bytes
    file_size = pdf_path.stat().st_size

    if file_size > MAX_SIZE:
        logger.warning(f"PDF {original_file_id} size ({file_size} bytes) exceeds 50MB limit. Skipping.")
        return [{
            "original_file_id": original_file_id,
            "product": None,
            "section": "",
            "function": "",
            "failure_mode": "",
            "status": "skipped_large_file",
            "error": f"File size {file_size} bytes exceeds 50MB limit",
        }]

    try:
        # Read PDF file as bytes
        pdf_bytes = pdf_path.read_bytes()

        # Prepare content with PDF file only (no additional user prompt)
        contents = [
            Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
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

        # Extract records from response
        records = result.get("records", [])

        if not records:
            logger.warning(f"No records extracted from {original_file_id}")
            return [{
                "original_file_id": original_file_id,
                "product": None,
                "section": "",
                "function": "",
                "failure_mode": "",
                "status": "success",
                "error": "No records extracted",
            }]

        # Expand records with original_file_id
        expanded_records = []
        for record in records:
            expanded_records.append({
                "original_file_id": original_file_id,
                "product": record.get("product"),
                "section": record.get("section", ""),
                "function": record.get("function", ""),
                "failure_mode": record.get("failure_mode", ""),
                "status": "success",
                "error": "",
            })

        logger.info(f"Successfully processed {original_file_id}: {len(expanded_records)} records extracted")
        return expanded_records

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for {original_file_id}: {e}")
        return [{
            "original_file_id": original_file_id,
            "product": None,
            "section": "",
            "function": "",
            "failure_mode": "",
            "status": "error",
            "error": f"JSON parse error: {str(e)}",
        }]

    except Exception as e:
        logger.error(f"Failed to process {original_file_id}: {e}")
        return [{
            "original_file_id": original_file_id,
            "product": None,
            "section": "",
            "function": "",
            "failure_mode": "",
            "status": "error",
            "error": str(e),
        }]


def collect_pdf_files(input_dir: Path) -> List[Path]:
    """Collect PDF files from input directory.

    Args:
        input_dir: Directory containing PDF files

    Returns:
        List of PDF file paths

    """
    pdf_files = sorted(input_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files in {input_dir}")
    return pdf_files


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_csv", type=click.Path(path_type=Path))
@click.option("--max-workers", default=4, type=int, help="Maximum number of parallel workers")
@click.option("--model", default=MODEL, help="Gemini model name")
def main(
    input_dir: Path,
    output_csv: Path,
    max_workers: int,
    model: str,
) -> None:
    """Extract attributes from PDF files and save to CSV.

    Args:
        input_dir: Directory containing PDF files
        output_csv: Output CSV file path
        max_workers: Maximum number of parallel workers (default: 4)
        model: Gemini model name (default: gemini-2.5-pro)

    """
    logger.info(f"Starting attribute extraction from PDF files in: {input_dir}")

    # Collect PDF files
    pdf_files = collect_pdf_files(input_dir)

    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return

    logger.info(f"Found {len(pdf_files)} PDF files to process")

    # Fetch prompt and schema from Langfuse
    system_instruction, response_schema = fetch_langfuse_prompt()

    # Create shared Gemini client
    client = mk_client(model)
    logger.info(f"Created Gemini client with model: {model}")

    # Process PDFs in parallel
    logger.info(f"Processing {len(pdf_files)} PDFs with {max_workers} parallel workers")
    all_records: List[Dict[str, Any]] = []

    # Create partial function with pre-bound arguments
    process_with_client = partial(
        process_single_pdf,
        client=client,
        system_instruction=system_instruction,
        response_schema=response_schema,
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_path = {executor.submit(process_with_client, path): path for path in pdf_files}

        # Collect results as they complete
        for i, future in enumerate(as_completed(future_to_path), 1):
            path = future_to_path[future]
            try:
                records = future.result()
                all_records.extend(records)
                logger.info(f"Progress: {i}/{len(pdf_files)} PDFs completed ({path.stem})")
            except Exception as e:
                logger.error(f"Failed to process {path.stem}: {e}")
                all_records.append({
                    "original_file_id": path.stem,
                    "product": None,
                    "section": "",
                    "function": "",
                    "failure_mode": "",
                    "status": "error",
                    "error": str(e),
                })

    # Save results to CSV
    if all_records:
        df_results = pd.DataFrame(all_records)

        # Select columns in the required order
        output_columns = [
            "original_file_id",
            "product",
            "section",
            "function",
            "failure_mode",
            "status",
            "error",
        ]
        df_output = df_results[output_columns].copy()

        # Ensure output directory exists
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        # Save to CSV
        df_output.to_csv(output_csv, index=False)
        logger.info(f"Results saved to: {output_csv}")
        logger.info(f"Total records: {len(all_records)}")

        # Summary statistics
        success_count = sum(1 for r in all_records if r["status"] == "success")
        skipped_count = sum(1 for r in all_records if r["status"] == "skipped_large_file")
        error_count = sum(1 for r in all_records if r["status"] == "error")

        # Count unique files processed
        unique_files = len(set(r["original_file_id"] for r in all_records))

        logger.info(
            f"Summary: {unique_files} files processed, "
            f"{success_count} records successful, "
            f"{skipped_count} skipped (too large), "
            f"{error_count} errors"
        )

        print(f"\n{'='*50}")
        print(f"Files processed: {unique_files}")
        print(f"Total records extracted: {len(all_records)}")
        print(f"Successful: {success_count}, Skipped: {skipped_count}, Errors: {error_count}")
        print(f"{'='*50}\n")

    else:
        logger.warning("No results to save")


if __name__ == "__main__":
    main()
