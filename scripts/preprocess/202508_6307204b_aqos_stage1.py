from pathlib import Path

import click
import pandas as pd
from dotenv import load_dotenv
from loguru import logger

load_dotenv()  # Load environment variables from .env file

# Filtering target values
TARGET_TYPES = [
    "クレーム通知書",
    "トラブル処置報告書",
    "仕様機能確認試験",
    "市場品質改善",
    "先行確認試験",
    "出荷検査",
    "初品検査",
    "品質不具合対応確認試験",
    "品質対策依頼書",
]


def filter_by_column(
    df: pd.DataFrame,
    input_csv: str,
    column_name: str,
    target_values: list,
    display_name: str,
) -> pd.DataFrame:
    """Filter dataframe by column values with logging and debugging"""
    if column_name not in df.columns:
        logger.info(f"No {column_name} column found - skipping {display_name} filtering")
        return df

    initial_count = len(df)
    filtered_df = df[df[column_name].isin(target_values)]
    filtered_count = len(filtered_df)

    logger.info(f"Filtered by {display_name}: {initial_count} -> {filtered_count} rows")
    logger.info(f"Target {display_name}: {target_values}")

    if filtered_count == 0:
        logger.warning(f"No rows match the specified {display_name} filter")

    return filtered_df


@click.command()
@click.argument("input_csv", type=click.Path(exists=True, dir_okay=False))
@click.argument("output_csv", type=click.Path(dir_okay=False))
def main(input_csv: str, output_csv: str):
    logger.info("Starting AQOS data filtering and renaming (Stage 1)")
    logger.info(f"Input file: {input_csv}")
    logger.info(f"Output file: {output_csv}")

    # Load CSV data
    logger.info("Loading CSV data...")
    df = pd.read_csv(input_csv, encoding="utf-8")
    logger.info(f"Loaded {len(df)} records")

    # Data cleaning
    logger.info("Cleaning data...")
    df = df.fillna("")

    # Apply filters
    df = filter_by_column(df, input_csv, "種類名", TARGET_TYPES, "種類名")

    # Clean text fields
    text_columns = [
        "部位(装置)",
        "表題",
        "内容",
        "原因",
        "対策",
        "再発防止",
        "種類名",
        "型式",
        "重要度",
        "案件NO",
    ]
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].astype(str)
            df[col] = df[col].str.replace("« NULL »", "", regex=False)
            df[col] = df[col].str.strip()
        else:
            logger.warning(f"Column '{col}' not found in the input data")

    # Rename columns to match Elasticsearch schema
    logger.info("Renaming columns to match Elasticsearch schema...")
    column_mapping = {
        "ID": "doc_id",
        "部位(装置)": "unit_original",
        "表題": "title",
        "内容": "content",
        "原因": "cause",
        "対策": "countermeasure",
        "再発防止": "recurrence_prevention",
        "種類名": "occurrence_step",
        "型式": "model_number",
        "重要度": "importance",
        "案件NO": "project_number",
    }

    # Apply column renaming
    columns_to_rename = {jp: en for jp, en in column_mapping.items() if jp in df.columns}
    if columns_to_rename:
        df = df.rename(columns=columns_to_rename)
        logger.info(f"Renamed columns: {columns_to_rename}")

    # Keep only columns that match Elasticsearch schema
    logger.info("Filtering columns to match Elasticsearch schema...")
    required_columns = [
        "doc_id",
        "unit_original",
        "title",
        "content",
        "cause",
        "countermeasure",
        "recurrence_prevention",
        "occurrence_step",
        "importance",
        "model_number",
        "project_number",
    ]

    # Find missing columns
    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        logger.warning(f"Missing required columns: {missing_cols}")
        # Add missing columns with empty values
        for col in missing_cols:
            df[col] = ""
            logger.info(f"Added missing column '{col}' with empty values")

    # Select only the required columns
    df = df[required_columns]
    logger.info(f"Kept columns: {list(df.columns)}")

    # Filter rows where content OR cause is empty (keep only rows with both fields populated)
    initial_count = len(df)
    df = df[(df["content"].str.len() > 0) & (df["cause"].str.len() > 0)]
    filtered_count = len(df)
    logger.info(f"Filtered rows with empty content or cause: {initial_count} -> {filtered_count} rows")

    # Save processed data
    logger.info("Saving filtered and renamed data...")
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")

    # Log final statistics
    logger.info("Stage 1 preprocessing completed successfully")
    logger.info(f"Processed {len(df)} records")
    logger.info(f"Final columns: {list(df.columns)}")
    logger.info(f"Output saved to: {output_csv}")
    logger.info("Ready for Stage 2: Attribute extraction with Gemini")


if __name__ == "__main__":
    main()
