#!/usr/bin/env python3
"""Cause_unit normalization script for AQOS data preprocessing.

This script normalizes cause_unit values using LLM-based classification
to map variant names to standardized unit categories.
"""

from pathlib import Path

import click
import pandas as pd
from google.genai.types import ThinkingConfig
from loguru import logger

from drassist.config import ConfigManager
from drassist.llm import GeminiClient


def load_unit_list():
    """Load standardized unit list from config file."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_path = project_root / "configs" / "6307204b.yaml"
    config = ConfigManager(str(config_path))
    return config.get("unit_list", [])


def load_data(input_csv: Path):
    """Load CSV data and identify units that need normalization."""
    logger.info(f"Reading data from: {input_csv}")
    df = pd.read_csv(input_csv, encoding="utf-8")

    unit_list = load_unit_list()
    classified_unq_units = df["cause_unit"].unique().tolist()
    diff_sets = list(set(classified_unq_units) - set(unit_list))

    logger.info(f"Total unique cause_units: {len(classified_unq_units)}")
    logger.info(f"Units needing normalization: {len(diff_sets)}")
    logger.info(f"Diff sets: {diff_sets}")

    return df, diff_sets, unit_list


def normalize_units_with_llm(diff_sets, unit_list):
    """Normalize units using GeminiClient LLM classification."""
    if not diff_sets:
        logger.info("No units need normalization.")
        return {}

    # Create system instruction for LLM classification
    unit_list_str = "\n".join([f"- {unit}" for unit in unit_list])
    system_instruction = f"""You are an expert classifier specializing in heavy machinery \
and construction equipment parts.

### Task

Your task is to classify a given "Part Unit Name" into the most appropriate category \
from the predefined list below.

### Predefined Class List

{unit_list_str}

### Instructions

1.  Analyze the input "Part Unit Name".
2.  Select the single most appropriate class from the "Predefined Class List".
3.  If an exact match is not available, choose the class that is semantically closest.
4.  Your output must be ONLY the name of the selected class. Do not provide any explanations or extra text.

"""

    # Initialize GeminiClient
    gemini_client = GeminiClient(
        model_name="gemini-2.5-flash",
        location="us-central1",
        temperature=0,
        seed=42,
    )

    # Process each unit in diff_sets
    excepted_unit_map = {}
    logger.info("Classifying units with LLM...")

    for idx, sample in enumerate(diff_sets):
        if pd.isna(sample):
            continue

        logger.info(f"Processing unit {idx + 1}/{len(diff_sets)}: {sample}")

        try:
            resp = gemini_client.generate_structured_content(
                prompt=sample,
                system_instruction=system_instruction,
                response_schema={
                    "type": "object",
                    "properties": {
                        "classification": {"type": "string", "description": "The classified unit name"}
                    },
                },
                thinking_config=ThinkingConfig(
                    thinking_budget=1024,
                ),
            )
            excepted_unit_map[sample] = resp["classification"]
        except Exception as e:
            logger.error(f"Failed to process unit '{sample}': {e}")
            # Skip failed units but continue processing
            continue

    # Validate all predictions are in unit_list
    for original, prediction in excepted_unit_map.items():
        if prediction not in unit_list:
            logger.warning(f"Unexpected classification for '{original}': '{prediction}'")
            raise ValueError(f"Classification '{prediction}' not in unit_list")

    logger.info(f"Successfully classified {len(excepted_unit_map)} units")
    return excepted_unit_map


def apply_normalization(df, excepted_unit_map, output_csv: Path, unit_list):
    """Apply normalization mapping to dataframe and save results."""
    # Create complete normalization mapping
    normalized_map = {unit: unit for unit in unit_list}
    normalized_map.update(excepted_unit_map)

    # Apply normalization
    df["normalized_cause_unit"] = df["cause_unit"].map(normalized_map)

    # Check for any unmapped units
    unmapped = df[df["normalized_cause_unit"].isna()]["cause_unit"].unique()
    if len(unmapped) > 0:
        logger.warning(f"{len(unmapped)} units could not be mapped: {unmapped}")

    # Save results
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")
    logger.info(f"Results saved to: {output_csv}")

    # Print statistics
    logger.info("Normalization Statistics:")
    logger.info(f"Original unique cause_units: {df['cause_unit'].nunique()}")
    logger.info(f"Normalized unique cause_units: {df['normalized_cause_unit'].nunique()}")
    logger.info(f"Reduction: {df['cause_unit'].nunique() - df['normalized_cause_unit'].nunique()}")

    return df


@click.command()
@click.argument(
    "input-csv",
    type=click.Path(exists=True, path_type=Path),
)
@click.argument(
    "output-csv",
    type=click.Path(path_type=Path),
)
def main(input_csv: Path, output_csv: Path):
    """Execute cause_unit normalization."""
    logger.info("Starting cause_unit normalization process (Stage 3)")

    # Load data and identify units needing normalization
    df, diff_sets, unit_list = load_data(input_csv)

    # Normalize units using LLM
    excepted_unit_map = normalize_units_with_llm(diff_sets, unit_list)

    # Apply normalization and save results
    df = apply_normalization(df, excepted_unit_map, output_csv, unit_list)

    logger.info("Cause_unit normalization completed successfully!")


if __name__ == "__main__":
    main()
