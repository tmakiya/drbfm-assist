#!/usr/bin/env python3

import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import Langfuse
from loguru import logger

from drassist.llm import GeminiClient

load_dotenv()

CATEGORY_LIST = [
    "ブーム装置",
    "ジブ伸縮機構（テレスコープ）",
    "ジブ取付・格納機構",
    "ジブ角度・チルト機構",
    "ラフィングジブ",
    "シングルトップジブ",
    "ブーム起伏装置",
    "折曲装置",
    "旋回装置",
    "ウインチ装置",
    "フック装置",
    "アウトリガ装置",
    "カウンタウエイト装置",
    "キャブ装置",
    "コックピット制御システム",
    "外装装置",
    "フレーム",
    "走行装置",
    "ドライブトレイン",
    "舵取装置",
    "制動装置",
    "緩衝装置",
    "エンジン系",
    "上部パワートレーン（ePTO）",
    "油圧装置",
    "空圧装置",
    "電装／電送装置",
    "充電装置",
    "照明装置",
    "空調装置",
    "過負荷防止装置（AML）",
    "動作規制装置（AMC）",
    "範囲規制装置（AWL）",
    "巻過防止・インタロック類",
    "アタッチメント装置",
    "バケット装置",
    "レベリング装置",
    "リフト装置",
    "ラジコン・リモコン装置",
    "コンクリート圧送装置",
    "塗装全般",
    "銘板装置",
    "低騒音装置",
    "牽引装置",
    "アシストカー",
    "パッケージ装置",
    "その他オプション",
]


def normalize_text(text: str) -> str:
    """Normalize text using Unicode normalization"""
    if pd.isna(text):
        return ""
    return unicodedata.normalize("NFKC", str(text).strip())


def process_record(
    record: pd.Series,
    client: GeminiClient,
    system_instruction: str,
    response_schema: dict,
) -> dict:
    """Process a single record for part categorization"""
    # Build text from 4 columns
    parts = []
    if record.get("part"):
        parts.append(f"Part Name: {normalize_text(record['part'])}")
    if record.get("title"):
        parts.append(f"Title: {normalize_text(record['title'])}")
    if record.get("content"):
        parts.append(f"Content: {normalize_text(record['content'])}")
    if record.get("cause"):
        parts.append(f"Cause: {normalize_text(record['cause'])}")

    text = "\n".join(parts)

    # Classify using Gemini
    result = client.generate_structured_content(
        prompt=text,
        response_schema=response_schema,
        system_instruction=system_instruction,
    )

    return {
        "doc_id": record.get("doc_id"),
        "result": result,
    }


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
    "--max-workers",
    type=int,
    default=8,
    help="Number of parallel workers",
)
def main(input_csv: Path, output_csv: Path, max_workers: int):
    """Execute part categorization for CSV data"""
    logger.info(f"Processing started: {input_csv}")

    category_list_str = "\n".join(f"* {category}" for category in sorted(CATEGORY_LIST))

    # Get prompt from Langfuse
    langfuse = Langfuse()
    langfuse_prompt = langfuse.get_prompt("Categorize part by pre-defined parts")
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile(category_list=category_list_str)

    logger.info("Prompt retrieved from Langfuse")
    logger.debug(f"Response schema: {response_schema}")

    # Read CSV
    df = pd.read_csv(input_csv, encoding="utf-8")
    logger.info(f"CSV loaded: {len(df)} records")

    # Check required columns
    required_columns = ["part", "title", "content", "cause"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.warning(f"Missing columns: {missing_columns}")

    # Initialize Gemini client
    client = GeminiClient()

    # Execute categorization with parallel processing
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
                logger.error(f"Failed to process record {idx}: {e}")
                failed_records.append(idx)
                results.append((idx, {"result": {"reasoning": "Error", "category": "Unknown"}}))

    logger.info(
        f"Categorization completed: {len(results) - len(failed_records)} succeeded, {len(failed_records)} failed"  # noqa: E501
    )

    results = pd.DataFrame([r[1] for r in results])
    df = df.merge(results, on="doc_id", how="left")

    df["part_category"] = df["result"].apply(lambda x: "" if isinstance(x, float) else x.get("category"))
    df.drop(columns=["result"], inplace=True)

    # Save as CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")
    logger.info(f"Results saved: {output_csv}")


if __name__ == "__main__":
    main()
