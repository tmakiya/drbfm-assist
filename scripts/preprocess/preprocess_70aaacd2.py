#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script processes XML files for '70aaacd2' data, extracts relevant information
using a large language model, and compiles it into a single CSV file.
The process involves:
1. Finding all XML files in a specified input directory.
2. For each XML file:
   - Reading its content.
   - Using a Gemini model with a specific prompt to extract structured data.
3. Performing post-processing on the extracted data to clean and structure it.
4. Saving the final data into a CSV file.
"""
import json
import uuid
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger
import typer
import xml.etree.ElementTree as ET

from drassist.llm.gemini_client import GeminiClient
from drassist.config.manager import ConfigManager

def find_xml_files(input_dir: str) -> List[Path]:
    """Finds all XML files in the input directory."""
    logger.info(f"Searching for XML files in {input_dir}")
    input_path = Path(input_dir)
    if not input_path.is_dir():
        logger.error(f"Input directory not found: {input_dir}")
        return []

    xml_files = list(input_path.glob("*.xml"))
    logger.info(f"Found {len(xml_files)} XML files.")
    return xml_files

def extract_data_from_xml_content(
    xml_content: str, file_name: str, prompt_path: str, gemini_client: GeminiClient
) -> List[Dict[str, Any]]:
    """Helper function to extract data from a single XML string."""
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except Exception as e:
        logger.error(f"Failed to read prompt file {prompt_path}: {e}")
        return []

    input_json = {"xml_content": xml_content, "file_name": file_name}

    try:
        system_instruction = prompt_template
        prompt_text = json.dumps(input_json, ensure_ascii=False, indent=2)

        raw_response = gemini_client.generate_content(
            prompt=prompt_text, system_instruction=system_instruction
        )

        cleaned_response = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
        extracted_data = json.loads(cleaned_response)

        logger.info(f"Extracted {len(extracted_data)} records from {file_name}.")
        return extracted_data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}\nRaw response: {raw_response}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred during extraction for {file_name}: {e}")
        return []

def save_data_to_csv(all_extracted_data: List[Dict[str, Any]], output_path: str):
    """Saves the extracted data to a CSV file after post-processing."""
    logger.info(f"Saving {len(all_extracted_data)} records to {output_path}")

    if not all_extracted_data:
        logger.warning("No data was extracted. Skipping CSV creation.")
        return

    df = pd.DataFrame(all_extracted_data)

    # Post-processing for cause_part and unit_part_change
    df['cause_part'] = ''
    df['unit_part_change'] = ''

    part_name = ''
    change_keywords = ['の追加', 'の削除', 'の加工', 'の穴']

    for i, row in df.iterrows():
        unit_original = row['unit_original']
        if not isinstance(unit_original, str):
            unit_original = ""

        is_change_point = any(keyword in unit_original for keyword in change_keywords)

        if not is_change_point and unit_original:
            part_name = unit_original
            df.loc[i, 'cause_part'] = part_name
        elif is_change_point:
            df.loc[i, 'cause_part'] = part_name
            df.loc[i, 'unit_part_change'] = unit_original
        else:
            df.loc[i, 'cause_part'] = part_name

    df = df[df['failure_mode'].str.strip() != '変更がもたらす機能の喪失, 商品性の欠如: なし\nその他:']

    if not df.empty and 'model_number' in df.columns and not df['model_number'].iloc[0] == "":
        model_number = df['model_number'].iloc[0]
        original_rows = len(df)
        df = df[df['unit_original'] != model_number]
        logger.info(f"Removed {original_rows - len(df)} rows where 'unit_original' matched 'model_number' ({model_number}).")

    expected_columns = [
        "doc_id", "unit_original", "title", "content", "cause", "countermeasure",
        "recurrence_prevention", "occurrence_step", "importance", "model_number", "project_number",
        "cause_unit", "cause_part", "unit_part_change", "occurrence_condition",
        "failure_mode", "failure_effect", "countermeasures", "reasoning"
    ]
    for col in expected_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[expected_columns]

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    logger.info(f"Successfully saved {len(df)} processed records to CSV.")

def main(
    config_id: str = typer.Option("70aaacd2", help="Configuration ID to use."),
    input_dir: Optional[str] = typer.Option(None, help="Directory containing XML files."),
    output_path: Optional[str] = typer.Option(None, help="Path for the output CSV file."),
    prompt_path: str = typer.Option("temp/extraction_prompt.txt", help="Path to the prompt file for extraction."),
):
    """
    Runs the XML to CSV conversion workflow for a given configuration.
    """
    logger.info(f"Starting XML to CSV workflow for config: {config_id}")

    config_path = f"configs/{config_id}.yaml"

    try:
        config_manager = ConfigManager(config_path)
        gemini_client = GeminiClient(**config_manager.llm)
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}.")
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        raise typer.Exit(code=1)

    _input_dir = input_dir or f"data/{config_id}/xml"
    _output_path = output_path or f"data/{config_id}/csv/defects.csv"

    xml_files = find_xml_files(_input_dir)
    if not xml_files:
        logger.warning("No XML files found, exiting.")
        return

    all_extracted_data: List[Dict[str, Any]] = []
    for file_path in xml_files:
        logger.info(f"Processing file: {file_path.name}")
        try:
            content = file_path.read_text(encoding="utf-8")
            extracted_data = extract_data_from_xml_content(
                content, file_path.name, prompt_path, gemini_client
            )
            if extracted_data:
                all_extracted_data.extend(extracted_data)
        except Exception as e:
            logger.error(f"Failed to process file {file_path}: {e}")

    if all_extracted_data:
        save_data_to_csv(all_extracted_data, _output_path)
        logger.info(f"Workflow completed successfully. Output saved to: {_output_path}")
    else:
        logger.warning("Workflow finished, but no data was extracted or saved.")

if __name__ == "__main__":
    typer.run(main)