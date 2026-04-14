#!/usr/bin/env python3
"""Batch Processing Script for DRBFM Purpose Workflow

Reads a CSV file with 'part' and 'change_point' columns,
runs the DRBFM Purpose workflow for each row,
and exports the results to a CSV file.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import click
import pandas as pd
from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm

from drassist.chains.drbfm_purpose_workflow import (
    DrbfmPurposeWorkflow,
    DrbfmPurposeWorkflowState,
)

load_dotenv()


def process_single_row(
    workflow: DrbfmPurposeWorkflow,
    part: str,
    change_point: str,
    row_index: int,
) -> List[Dict[str, Any]]:
    """Process a single row and return list of generated failure modes"""
    logger.info(f"Processing row {row_index}: part='{part[:30]}...', change_point='{change_point[:30]}...'")

    try:
        # Create initial state
        initial_state = DrbfmPurposeWorkflowState(
            part=part,
            change_point=change_point,
        )

        # Run workflow
        result = workflow.invoke(
            initial_state,
            config={"run_name": f"DRBFM Purpose Workflow - Row {row_index}"}
        )

        # Extract generated failure modes and mapped section/function_category
        generated_failure_modes = result.get("generated_failure_modes", [])
        input_section = result.get("input_section", "")
        input_function_category = result.get("input_function_category", "")

        # Convert to list of dicts with input info
        output_rows = []
        for fm in generated_failure_modes:
            # Create base row with input and generated content
            base_row = {
                "input_part": part,
                "input_change_point": change_point,
                "input_section": input_section,
                "input_function_category": input_function_category,
                "failure_mode": fm.failure_mode,
                "cause": fm.cause,
                "effect": fm.effect,
                "countermeasure": fm.countermeasure,
                "reasoning": fm.reasoning,
                "propriety": fm.propriety,
                "propriety_reasoning": fm.propriety_reasoning,
            }

            # If there are references, create a row for each reference
            if fm.references:
                for ref in fm.references:
                    row = base_row.copy()
                    row.update({
                        "source_type": ref.source_type,
                        "source_id": ref.source_id,
                        "source_URL": ref.source_URL,
                        "source_section": ref.source_section,
                        "source_part": ref.source_part,
                        "source_function_category": ref.source_function_category,
                        "source_function": ref.source_function,
                        "source_change_point": ref.source_change_point,
                        "source_failure_mode": ref.source_failure_mode,
                        "source_cause": ref.source_cause,
                        "source_effect": ref.source_effect,
                        "source_countermeasure": ref.source_countermeasure,
                    })
                    output_rows.append(row)
            else:
                # No references - still output the generated failure mode
                row = base_row.copy()
                row.update({
                    "source_type": "",
                    "source_id": "",
                    "source_URL": "",
                    "source_section": "",
                    "source_part": "",
                    "source_function_category": "",
                    "source_function": "",
                    "source_change_point": "",
                    "source_failure_mode": "",
                    "source_cause": "",
                    "source_effect": "",
                    "source_countermeasure": "",
                })
                output_rows.append(row)

        # If no results, still output a row with empty fields
        if not output_rows:
            output_rows.append({
                "input_part": part,
                "input_change_point": change_point,
                "input_section": input_section,
                "input_function_category": input_function_category,
                "failure_mode": "",
                "cause": "",
                "effect": "",
                "countermeasure": "",
                "reasoning": "",
                "source_type": "",
                "source_id": "",
                "source_URL": "",
                "source_section": "",
                "source_part": "",
                "source_function_category": "",
                "source_function": "",
                "source_change_point": "",
                "source_failure_mode": "",
                "source_cause": "",
                "source_effect": "",
                "source_countermeasure": "",
            })

        logger.info(f"Row {row_index}: Generated {len(generated_failure_modes)} failure modes")
        return output_rows

    except Exception as e:
        logger.error(f"Error processing row {row_index}: {e}")
        return [{
            "input_part": part,
            "input_change_point": change_point,
            "input_section": "",
            "input_function_category": "",
            "failure_mode": "",
            "cause": "",
            "effect": "",
            "countermeasure": "",
            "reasoning": "",
            "source_type": "",
            "source_id": "",
            "source_URL": "",
            "source_section": "",
            "source_part": "",
            "source_function_category": "",
            "source_function": "",
            "source_change_point": "",
            "source_failure_mode": "",
            "source_cause": "",
            "source_effect": "",
            "source_countermeasure": "",
            "error": str(e),
        }]


@click.command()
@click.argument("input_csv", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output-csv",
    type=click.Path(dir_okay=False),
    default=None,
    help="Output CSV file path. If not specified, generates based on input filename.",
)
@click.option(
    "--config-path",
    type=click.Path(exists=True, dir_okay=False),
    default="configs/drbfm_purpose.yaml",
    help="Path to configuration file",
)
@click.option(
    "--part-column",
    type=str,
    default="部品",
    help="Column name for part in input CSV",
)
@click.option(
    "--change-point-column",
    type=str,
    default="変更点（変更内容・目的）",
    help="Column name for change_point in input CSV",
)
def main(
    input_csv: str,
    output_csv: str,
    config_path: str,
    part_column: str,
    change_point_column: str,
):
    """Run DRBFM Purpose workflow for each row in input CSV"""
    logger.info(f"Starting batch processing for: {input_csv}")

    # Load input CSV
    input_path = Path(input_csv)
    df = pd.read_csv(input_path, encoding="utf-8")
    logger.info(f"Loaded {len(df)} rows from {input_csv}")

    # Validate columns
    if part_column not in df.columns:
        raise ValueError(f"Column '{part_column}' not found in input CSV. Available columns: {list(df.columns)}")
    if change_point_column not in df.columns:
        raise ValueError(f"Column '{change_point_column}' not found in input CSV. Available columns: {list(df.columns)}")

    # Initialize workflow
    logger.info("Initializing DRBFM Purpose workflow...")
    workflow = DrbfmPurposeWorkflow(config_path=config_path)

    # Process each row
    all_results = []
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing rows"):
        part = str(row[part_column]) if pd.notna(row[part_column]) else ""
        change_point = str(row[change_point_column]) if pd.notna(row[change_point_column]) else ""

        if not part or not change_point:
            logger.warning(f"Skipping row {idx}: empty part or change_point")
            all_results.append({
                "input_part": part,
                "input_change_point": change_point,
                "input_section": "",
                "input_function_category": "",
                "failure_mode": "",
                "cause": "",
                "effect": "",
                "countermeasure": "",
                "reasoning": "",
                "source_type": "",
                "source_id": "",
                "source_URL": "",
                "source_section": "",
                "source_part": "",
                "source_function_category": "",
                "source_function": "",
                "source_change_point": "",
                "source_failure_mode": "",
                "source_cause": "",
                "source_effect": "",
                "source_countermeasure": "",
                "error": "Empty part or change_point",
            })
            continue

        results = process_single_row(workflow, part, change_point, idx)
        all_results.extend(results)

    # Create output DataFrame
    output_df = pd.DataFrame(all_results)

    # Reorder columns for better readability
    column_order = [
        "input_part",
        "input_change_point",
        "input_section",
        "input_function_category",
        "failure_mode",
        "cause",
        "effect",
        "countermeasure",
        "reasoning",
        "propriety",
        "propriety_reasoning",
        "source_type",
        "source_id",
        "source_URL",
        "source_section",
        "source_part",
        "source_function_category",
        "source_function",
        "source_change_point",
        "source_failure_mode",
        "source_cause",
        "source_effect",
        "source_countermeasure",
    ]
    # Add error column if it exists
    if "error" in output_df.columns:
        column_order.append("error")
    
    # Only include columns that exist
    column_order = [col for col in column_order if col in output_df.columns]
    output_df = output_df[column_order]

    # Determine output path
    if output_csv is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = input_path.parent / f"{input_path.stem}_output_{timestamp}.csv"

    # Save output
    output_df.to_csv(output_csv, index=False, encoding="utf-8")
    logger.info(f"Saved {len(output_df)} rows to {output_csv}")

    # Summary
    total_inputs = len(df)
    total_outputs = len(output_df)
    inputs_with_results = output_df[output_df["failure_mode"] != ""]["input_part"].nunique()

    logger.info("=" * 50)
    logger.info("Batch Processing Summary")
    logger.info("=" * 50)
    logger.info(f"Total input rows: {total_inputs}")
    logger.info(f"Total output rows: {total_outputs}")
    logger.info(f"Inputs with generated failure modes: {inputs_with_results}/{total_inputs}")
    logger.info(f"Output file: {output_csv}")


if __name__ == "__main__":
    main()
