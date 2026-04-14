import unicodedata
from pathlib import Path

import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import get_client
from loguru import logger

from drassist.llm.gemini_client import GeminiClient

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

TARGET_IMPORTANCE = ["A", "B", "C"]


def normalize_parts_hierarchically(unique_parts: list) -> dict:
    """Normalize parts using hierarchical categorization with Gemini AI"""
    logger.info("Starting hierarchical parts normalization...")

    # Apply Unicode normalization
    normalized_parts = [unicodedata.normalize("NFKC", part) for part in unique_parts]

    # Initialize Gemini client
    gemini_client = GeminiClient(model_name="gemini-2.5-pro")

    langfuse_client = get_client()
    langfuse_prompt = langfuse_client.get_prompt("Normalize parts")

    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    # Generate hierarchical categorization
    prompt = str(normalized_parts)
    response = gemini_client.generate_structured_content(
        prompt, response_schema, system_instruction=system_instruction
    )

    logger.info(
        f"Successfully categorized {len(normalized_parts)} parts into {len(response['categorization_result'])} major categories"  # noqa: E501
    )
    return response


def create_part_mapping(hierarchical_data: dict) -> dict:
    """Create mapping from original parts to normalized categories"""
    logger.info("Creating part normalization mapping...")

    mapping = {}
    categorization_result = hierarchical_data["categorization_result"]

    for category in categorization_result:
        category_name = category["category_name"]

        for sub_category in category["sub_categories"]:
            sub_category_name = sub_category["sub_category_name"]

            for item in sub_category["items"]:
                # Apply Unicode normalization to the item
                normalized_item = unicodedata.normalize("NFKC", item)

                mapping[item] = {
                    "part_normalized": normalized_item,
                    "part_category": category_name,
                    "part_sub_category": sub_category_name,
                }

    logger.info(f"Created mapping for {len(mapping)} parts")
    return mapping


def apply_part_normalization(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Apply part normalization to dataframe"""
    logger.info("Applying part normalization to dataframe...")

    # Initialize new columns
    df["part_normalized"] = ""
    df["part_category"] = ""
    df["part_sub_category"] = ""

    # Apply mapping
    for index, row in df.iterrows():
        part = row["part"]
        if part in mapping:
            df.at[index, "part_normalized"] = mapping[part]["part_normalized"]
            df.at[index, "part_category"] = mapping[part]["part_category"]
            df.at[index, "part_sub_category"] = mapping[part]["part_sub_category"]
        else:
            # Fallback: use original part as normalized
            df.at[index, "part_normalized"] = unicodedata.normalize("NFKC", part)
            df.at[index, "part_category"] = "Unknown"
            df.at[index, "part_sub_category"] = "Unknown"

    logger.info("Part normalization applied successfully")
    return df


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
    logger.info("Starting preprocessing for case 202507_6307204b")
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
    df = filter_by_column(df, input_csv, "重要度", TARGET_IMPORTANCE, "重要度")

    # Clean text fields
    text_columns = [
        "部位(装置)",
        "原因",
        "表題",
        "内容",
        "対策",
        "再発防止",
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
        "部位(装置)": "part",
        "表題": "title",
        "内容": "content",
        "原因": "cause",
        "対策": "countermeasure",
        "再発防止": "recurrence_prevention",
        "重要度": "importance",
    }

    # Apply column renaming
    columns_to_rename = {jp: en for jp, en in column_mapping.items() if jp in df.columns}
    if columns_to_rename:
        df = df.rename(columns=columns_to_rename)
        logger.info(f"Renamed columns: {columns_to_rename}")

    # Hierarchical parts normalization (after column renaming)
    logger.info("Starting parts hierarchical normalization...")

    # Get unique parts for normalization
    unique_parts = df["part"].unique().tolist()
    unique_parts = [part for part in unique_parts if part and str(part).strip()]

    logger.info(f"Found {len(unique_parts)} unique parts for normalization")

    if unique_parts:
        # Perform hierarchical normalization
        hierarchical_data = normalize_parts_hierarchically(unique_parts)

        # Create mapping
        part_mapping = create_part_mapping(hierarchical_data)

        # Apply normalization to dataframe
        df = apply_part_normalization(df, part_mapping)

        # Log normalization statistics
        category_counts = df["part_category"].value_counts()
        logger.info(f"Parts categorized into {len(category_counts)} major categories:")
        for category, count in category_counts.items():
            logger.info(f"  {category}: {count} parts")

    # Keep only columns that match Elasticsearch schema (including normalization columns)
    logger.info("Filtering columns to match Elasticsearch schema...")
    required_columns = [
        "doc_id",
        "part",
        "title",
        "content",
        "cause",
        "countermeasure",
        "recurrence_prevention",
        "importance",
    ]

    # Add normalization columns if they exist
    normalization_columns = ["part_normalized", "part_category", "part_sub_category"]
    for col in normalization_columns:
        if col in df.columns:
            required_columns.append(col)

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

    # Filter by non-empty content columns (exclude doc_id)
    content_columns = [col for col in required_columns if col != "doc_id"]
    for col in content_columns:
        initial_count = len(df)
        df = df[df[col].str.len() > 0]

        filtered_count = len(df)
        logger.info(f"Filtered by non-empty {col}: {initial_count} -> {filtered_count} rows")

    # Save processed data
    logger.info("Saving processed data...")
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")

    # Log final statistics
    logger.info("Preprocessing completed successfully")
    logger.info(f"Processed {len(df)} records")
    logger.info(f"Final columns: {list(df.columns)}")

    # Log normalization statistics if available
    if "part_normalized" in df.columns:
        unique_original_parts = df["part"].nunique()
        unique_normalized_parts = df["part_normalized"].nunique()
        unique_categories = df["part_category"].nunique()
        unique_sub_categories = df["part_sub_category"].nunique()

        logger.info("Parts normalization summary:")
        logger.info(f"  Original unique parts: {unique_original_parts}")
        logger.info(f"  Normalized unique parts: {unique_normalized_parts}")
        logger.info(f"  Major categories: {unique_categories}")
        logger.info(f"  Sub-categories: {unique_sub_categories}")

        reduction_rate = (
            (1 - unique_normalized_parts / unique_original_parts) * 100 if unique_original_parts > 0 else 0
        )
        logger.info(f"  Parts reduction rate: {reduction_rate:.1f}%")

    logger.info(f"Output saved to: {output_csv}")


if __name__ == "__main__":
    main()
