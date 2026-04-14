#!/usr/bin/env python3
"""Add section prefix to design changes CSV

Reads the design changes CSV and adds the "部位N: " prefix to the section column
to match the format used in DRBFM and failure report data.
"""
import pandas as pd
from loguru import logger

# Mapping from section name to prefixed section name
SECTION_PREFIX_MAP = {
    "筐体・外装／取付・配管接続部": "部位1: 筐体・外装／取付・配管接続部",
    "給水・給湯・ふろ循環の水回路＋熱交換部": "部位2: 給水・給湯・ふろ循環の水回路＋熱交換部",
    "燃焼・給気・排気部": "部位3: 燃焼・給気・排気部",
    "ガス供給・ガス制御部": "部位4: ガス供給・ガス制御部",
    "電装・制御ロジック部": "部位5: 電装・制御ロジック部",
    "センサー・安全保安装置部": "部位6: センサー・安全保安装置部",
    "リモコン・ユーザーインターフェース＋付属部": "部位7: リモコン・ユーザーインターフェース＋付属部",
}


def main():
    input_file = "data/purpose/design_changes/design_changes_attributes.csv"

    logger.info(f"Reading CSV file: {input_file}")
    df = pd.read_csv(input_file)

    # Check current section values
    unique_sections = df["section"].unique()
    logger.info(f"Found {len(unique_sections)} unique section values")

    # Apply mapping
    df["section"] = df["section"].map(SECTION_PREFIX_MAP)

    # Check for unmapped values
    unmapped = df[df["section"].isna()]
    if len(unmapped) > 0:
        logger.warning(f"Found {len(unmapped)} rows with unmapped section values")

    # Save updated CSV
    df.to_csv(input_file, index=False)
    logger.info(f"Updated {len(df)} rows and saved to {input_file}")

    # Show sample of updated values
    logger.info("Sample of updated section values:")
    for section in df["section"].unique()[:5]:
        logger.info(f"  - {section}")


if __name__ == "__main__":
    main()
