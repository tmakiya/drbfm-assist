#!/usr/bin/env python3
"""Cause_part normalization script for AQOS data preprocessing.

This script normalizes cause_part values by applying text normalization
and notation variation mapping to standardize part names.
"""

from pathlib import Path

import click
import pandas as pd
from loguru import logger

from drassist.config.manager import ConfigManager
from drassist.text.normalizer import basic_normalize_text, build_longest_subber


def load_data(input_csv: Path):
    """Load CSV data and validate required columns."""
    logger.info(f"Reading data from: {input_csv}")

    df = pd.read_csv(input_csv, encoding="utf-8")

    # Validate required columns
    if "cause_part" not in df.columns:
        raise ValueError("Required column 'cause_part' not found in CSV file")

    logger.info(f"Loaded {len(df)} records from CSV")
    logger.info(f"Original unique cause_parts: {df['cause_part'].nunique()}")

    return df


def normalize_cause_parts(df, config_manager):
    """Apply normalization to cause_part column."""
    logger.info("Applying cause_part normalization...")

    # Get normalization dictionary from configuration
    normalized_dict = config_manager.get("normalized_notation_dict", {})
    subber = build_longest_subber(normalized_dict)

    # Apply notation variation substitution
    logger.info("Applying notation variation substitution...")

    def _normalize(cause_part):
        if pd.isna(cause_part) or cause_part == "":
            return cause_part
        cause_part = eval(cause_part)
        cause_part = [subber(basic_normalize_text(p)) for p in cause_part]
        return cause_part

    df["normalized_cause_part"] = df["cause_part"].apply(_normalize)

    return df


def save_results(df, output_csv: Path):
    """Save normalized results to CSV file."""
    # Create output directory if it doesn't exist
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    df["cause_part"] = df["normalized_cause_part"]
    df["cause_unit"] = df["normalized_cause_unit"]
    df.drop(["normalized_cause_unit", "normalized_cause_part"], axis=1, inplace=True)

    # Save to CSV
    df.to_csv(output_csv, index=False, encoding="utf-8")
    logger.info(f"Results saved to: {output_csv}")


@click.command()
@click.argument(
    "input-csv",
    type=click.Path(exists=True, path_type=Path),
)
@click.argument(
    "output-csv",
    type=click.Path(path_type=Path),
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="configs/6307204b.yaml",
    help="Configuration file path",
)
def main(input_csv: Path, output_csv: Path, config: Path):
    """Execute cause_part normalization."""
    logger.info("Starting cause_part normalization process")

    # Initialize configuration manager
    config_manager = ConfigManager(str(config))

    # Load data
    df = load_data(input_csv)

    # Apply normalization
    df = normalize_cause_parts(df, config_manager)

    # Save results
    save_results(df, output_csv)

    logger.info("Cause_part normalization completed successfully!")


if __name__ == "__main__":
    main()
