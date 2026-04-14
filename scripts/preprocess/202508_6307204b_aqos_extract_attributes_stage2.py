import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import Langfuse
from loguru import logger

from drassist.config import ConfigManager
from drassist.llm import GeminiClient

load_dotenv()  # Load environment variables from .env file


def load_unit_list():
    """Load standardized unit list from config file."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_path = project_root / "configs" / "6307204b.yaml"
    config = ConfigManager(str(config_path))
    return config.get("unit_list", [])


def process_record(
    record: pd.Series,
    client: GeminiClient,
    system_instruction: str,
    response_schema: dict,
) -> dict:
    """Process a single record with Gemini API to extract attributes"""
    try:
        # Build user prompt with the specified schema
        user_prompt = {
            "unit_original": str(record.get("unit_original", "")),
            "title": str(record.get("title", "")),
            "content": str(record.get("content", "")),
            "cause": str(record.get("cause", "")),
            "countermeasure": str(record.get("countermeasure")),
            "recurrence_prevention": str(record.get("recurrence_prevention")),
        }

        # Convert to JSON string for the prompt
        prompt_text = json.dumps(user_prompt, ensure_ascii=False, indent=2)

        # Call Gemini API
        result = client.generate_structured_content(
            prompt=prompt_text,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        # Add doc_id to result for merging
        result["doc_id"] = record.get("doc_id")

        return result

    except Exception as e:
        logger.error(f"Failed to process record {record.get('doc_id', 'unknown')}: {e}")
        # Return empty result with doc_id for failed records
        return {"doc_id": record.get("doc_id")}


@click.command()
@click.argument("input_csv", type=click.Path(exists=True, dir_okay=False))
@click.argument("output_csv", type=click.Path(dir_okay=False))
@click.option("--test", is_flag=True, help="Test mode: process only 50 random samples")
@click.option("--max-workers", type=int, default=8, help="Number of parallel workers")
def main(input_csv: str, output_csv: str, test: bool, max_workers: int):
    logger.info("Starting AQOS attribute extraction with Gemini (Stage 2)")
    logger.info(f"Input file: {input_csv}")
    logger.info(f"Output file: {output_csv}")
    if test:
        logger.info("Running in TEST MODE - will process 50 random samples")

    # Load filtered CSV data from Stage 1
    logger.info("Loading filtered CSV data from Stage 1...")
    df = pd.read_csv(input_csv, encoding="utf-8")
    logger.info(f"Loaded {len(df)} records")

    # Verify required columns exist
    required_columns = ["doc_id", "unit_original", "title", "content", "cause"]
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        logger.error(f"Missing required columns: {missing_cols}")
        logger.error("Please ensure the input CSV is the output from Stage 1 preprocessing")
        return

    # Test mode: sample 50 random rows
    if test:
        sample_size = min(20, len(df))
        df = df.sample(n=sample_size, random_state=42)
        logger.info(f"Test mode: Sampled {len(df)} random rows for processing")

    # Get prompt from Langfuse
    logger.info("Fetching prompt from Langfuse...")
    langfuse = Langfuse()
    langfuse_prompt = langfuse.get_prompt("extract_attributes_from_failure_record")
    response_schema = langfuse_prompt.config["response_schema"]

    # Load unit list from config and prepare for prompt
    unit_list = load_unit_list()
    unit_list_str = "\n".join(f"- {unit}" for unit in unit_list)
    system_instruction = langfuse_prompt.compile(unit_list=unit_list_str)

    logger.info("Prompt retrieved from Langfuse")
    logger.debug(f"Response schema: {response_schema}")

    # Initialize Gemini client
    logger.info("Initializing Gemini client...")
    client = GeminiClient(model_name="gemini-2.5-pro")

    # Process records with Gemini API using parallel processing
    logger.info(f"Starting Gemini processing with {max_workers} workers...")
    results = []
    failed_records = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks
        future_to_index = {
            executor.submit(
                process_record,
                row,
                client,
                system_instruction,
                response_schema,
            ): idx
            for idx, row in df.iterrows()
        }

        # Collect results
        completed = 0
        total = len(df)

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            completed += 1

            try:
                result = future.result()
                results.append((idx, result))

                if completed % 10 == 0:
                    logger.info(f"Progress: {completed}/{total} records completed")

            except Exception as e:
                logger.error(f"Failed to process record at index {idx}: {e}")
                failed_records.append(idx)
                # Add a placeholder result for failed records
                results.append((idx, {"doc_id": df.loc[idx, "doc_id"]}))

    logger.info(
        f"Gemini processing completed: {len(results) - len(failed_records)} succeeded, "
        f"{len(failed_records)} failed"
    )

    # Sort results by index to maintain order
    results.sort(key=lambda x: x[0])

    # Create DataFrame from results
    results_df = pd.DataFrame([r[1] for r in results])

    # Merge results with original dataframe
    if not results_df.empty and "doc_id" in results_df.columns:
        # Get all columns from results except doc_id
        result_columns = [col for col in results_df.columns if col != "doc_id"]

        # Merge on doc_id
        df = df.merge(results_df, on="doc_id", how="left")

        logger.info(f"Added {len(result_columns)} new fields from Gemini: {result_columns}")
    else:
        logger.warning("No results to merge from Gemini processing")

    # Save processed data
    logger.info("Saving data with extracted attributes...")
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")

    # Log final statistics
    logger.info("Stage 2 attribute extraction completed successfully")
    logger.info(f"Processed {len(df)} records")
    logger.info(f"Final columns: {list(df.columns)}")
    logger.info(f"Output saved to: {output_csv}")


if __name__ == "__main__":
    main()
