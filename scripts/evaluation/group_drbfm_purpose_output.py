#!/usr/bin/env python3
"""Group DRBFM Purpose Workflow Output

Groups rows from run_drbfm_purpose_workflow.py output by:
- input_part, input_change_point, failure_mode, cause, effect, countermeasure, reasoning

Aggregation rules:
- propriety: False if any row has False, otherwise True
- propriety_reasoning: unique values joined by ","
- source_* columns: aggregated as JSON array
"""
import json
from pathlib import Path
from typing import List, Dict, Any

import click
import pandas as pd
from loguru import logger


# Columns used for grouping
GROUP_COLUMNS = [
    "input_part",
    "input_change_point",
    "failure_mode",
    "cause",
    "effect",
    "countermeasure",
    "reasoning",
]

# Reference columns to aggregate as array
REFERENCE_COLUMNS = [
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


def aggregate_propriety(series: pd.Series) -> bool:
    """Aggregate propriety: False if any is False, otherwise True"""
    # Handle various representations of False
    for val in series:
        if val is False or val == "False" or val == "false" or val == 0:
            return False
    return True


def aggregate_propriety_reasoning(series: pd.Series) -> str:
    """Aggregate propriety_reasoning: unique values joined by comma"""
    unique_values = series.dropna().unique()
    # Filter out empty strings
    unique_values = [str(v) for v in unique_values if str(v).strip()]
    return ", ".join(unique_values)


def aggregate_references(group_df: pd.DataFrame) -> str:
    """Aggregate reference columns as JSON array"""
    references = []
    for _, row in group_df.iterrows():
        ref = {}
        has_value = False
        for col in REFERENCE_COLUMNS:
            if col in row and pd.notna(row[col]) and str(row[col]).strip():
                ref[col] = str(row[col])
                has_value = True
            else:
                ref[col] = ""
        if has_value:
            references.append(ref)
    
    if not references:
        return "[]"
    return json.dumps(references, ensure_ascii=False)


def group_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Group dataframe by specified columns and aggregate"""
    logger.info(f"Grouping {len(df)} rows by {GROUP_COLUMNS}")
    
    # Ensure all group columns exist
    for col in GROUP_COLUMNS:
        if col not in df.columns:
            logger.warning(f"Column '{col}' not found, using empty string")
            df[col] = ""
    
    # Fill NaN with empty string for grouping
    df_filled = df.fillna("")
    
    # Group and aggregate
    grouped_rows = []
    for group_key, group_df in df_filled.groupby(GROUP_COLUMNS, dropna=False):
        # Create row with group key values
        row = dict(zip(GROUP_COLUMNS, group_key))
        
        # Add input_section and input_function_category (take first value)
        if "input_section" in group_df.columns:
            row["input_section"] = group_df["input_section"].iloc[0]
        if "input_function_category" in group_df.columns:
            row["input_function_category"] = group_df["input_function_category"].iloc[0]
        
        # Aggregate propriety
        if "propriety" in group_df.columns:
            row["propriety"] = aggregate_propriety(group_df["propriety"])
        
        # Aggregate propriety_reasoning
        if "propriety_reasoning" in group_df.columns:
            row["propriety_reasoning"] = aggregate_propriety_reasoning(group_df["propriety_reasoning"])
        
        # Aggregate references
        row["references"] = aggregate_references(group_df)
        
        grouped_rows.append(row)
    
    result_df = pd.DataFrame(grouped_rows)
    logger.info(f"Grouped to {len(result_df)} rows")
    
    # Reorder columns
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
        "references",
    ]
    column_order = [col for col in column_order if col in result_df.columns]
    result_df = result_df[column_order]
    
    return result_df


@click.command()
@click.argument("input_csv", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output-csv",
    type=click.Path(dir_okay=False),
    required=True,
    help="Output CSV file path for grouped results",
)
def main(input_csv: str, output_csv: str):
    """Group DRBFM Purpose workflow output by failure mode attributes"""
    logger.info(f"Loading input CSV: {input_csv}")
    
    # Load input CSV
    df = pd.read_csv(input_csv, encoding="utf-8")
    logger.info(f"Loaded {len(df)} rows")
    
    # Group dataframe
    grouped_df = group_dataframe(df)
    
    # Save output
    output_path = Path(output_csv)
    grouped_df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info(f"Saved {len(grouped_df)} grouped rows to {output_csv}")
    
    # Summary
    logger.info("=" * 50)
    logger.info("Grouping Summary")
    logger.info("=" * 50)
    logger.info(f"Input rows: {len(df)}")
    logger.info(f"Output rows: {len(grouped_df)}")
    logger.info(f"Reduction: {len(df) - len(grouped_df)} rows ({(1 - len(grouped_df)/len(df))*100:.1f}%)")


if __name__ == "__main__":
    main()
