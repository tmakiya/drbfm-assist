#!/usr/bin/env python3
"""Data Ingestion Script for DRBFM Assist Prototype
Loads AQOS data from CSV, generates embeddings and indexes to Elasticsearch
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import pandas as pd
from dotenv import load_dotenv
from loguru import logger

# Import from drassist package
from drassist.config import ConfigManager
from drassist.elasticsearch import ElasticsearchManager
from drassist.embeddings import AzureOpenAIEmbedder

load_dotenv()  # Load environment variables from .env file


class DataProcessor:
    """CSV data processing and preparation"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.data_file = Path(config.data["file_path"])

    def get_allowed_fields_from_mapping(self, es_manager: ElasticsearchManager) -> set:
        """Get allowed fields from Elasticsearch mapping"""
        mapping = es_manager.load_mapping()
        properties = mapping.get("mappings", {}).get("properties", {})

        # Extract field names, excluding nested objects that will be handled separately
        allowed_fields = set()
        for field_name, field_config in properties.items():
            if field_name not in ["cause", "failure", "embedding"]:  # These are handled separately
                allowed_fields.add(field_name)

        return allowed_fields

    def load_data(self) -> pd.DataFrame:
        """Load CSV data"""
        if not self.data_file.exists():
            raise FileNotFoundError(f"Data file not found: {self.data_file}")

        df = pd.read_csv(self.data_file, encoding="utf-8")
        logger.info(f"Loaded {len(df)} records from {self.data_file}")

        # Use existing doc_id column if present, otherwise create from index
        if "doc_id" in df.columns:
            df["doc_id"] = df["doc_id"].astype(int)  # Ensure doc_id is integer type
        else:
            df = df.reset_index()
            df = df.rename(columns={"index": "doc_id"})
        logger.info("Using existing doc_id column from preprocessed data")

        df.fillna("", inplace=True)  # Fill NaN values with empty strings

        return df

    def prepare_documents(
        self, df: pd.DataFrame, embeddings: List[Optional[List[float]]], es_manager: ElasticsearchManager
    ) -> List[Dict[str, Any]]:
        """Prepare documents for Elasticsearch indexing"""
        # Get allowed fields from Elasticsearch mapping
        allowed_fields = self.get_allowed_fields_from_mapping(es_manager)

        documents = []

        for idx, row in df.iterrows():
            doc = row.to_dict()

            # Create cause hierarchical structure
            cause_data = {
                "original": doc.pop("cause", ""),
                "unit": doc.pop("cause_unit", ""),
                "part": doc.pop("cause_part", ""),
                "part_change": doc.pop("unit_part_change", ""),
            }
            if isinstance(cause_data["part"], str) and cause_data["part"] != "":
                cause_data["part"] = eval(cause_data["part"])

            # Create failure hierarchical structure
            failure_data = {"mode": doc.pop("failure_mode", ""), "effect": doc.pop("failure_effect", "")}

            # Filter document to only include allowed fields
            filtered_doc = {key: value for key, value in doc.items() if key in allowed_fields}

            # Add structured data
            filtered_doc["cause"] = cause_data
            filtered_doc["failure"] = failure_data

            # Add embedding
            if embeddings[idx]:
                filtered_doc["embedding"] = embeddings[idx]

            documents.append(filtered_doc)

        logger.info(f"Prepared {len(documents)} documents for indexing")
        return documents


@click.command()
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
def main(config_path: Path):
    logger.info("Starting data ingestion process")

    # Initialize configuration
    config = ConfigManager(config_path)
    logger.info("Configuration loaded successfully")

    # Initialize components
    data_processor = DataProcessor(config)
    embedder = AzureOpenAIEmbedder(config)
    es_manager = ElasticsearchManager(config)

    # Load and preprocess data
    logger.info("Loading and preprocessing data...")
    df = data_processor.load_data()

    # Generate embeddings
    logger.info("Generating embeddings...")
    embedding_texts = df["unit_part_change"].tolist()

    # Filter out empty strings and replace with None to skip embedding generation
    processed_texts = []
    for text in embedding_texts:
        if text and str(text).strip():  # Check for non-empty text
            processed_texts.append(str(text).strip())
        else:
            processed_texts.append(None)

    # Generate embeddings only for non-None texts
    non_empty_texts = [text for text in processed_texts if text is not None]
    non_empty_embeddings = embedder.generate_embeddings_batch(non_empty_texts) if non_empty_texts else []

    # Map embeddings back to original positions
    embeddings = []
    non_empty_index = 0
    for text in processed_texts:
        if text is not None:
            embeddings.append(
                non_empty_embeddings[non_empty_index] if non_empty_index < len(non_empty_embeddings) else None
            )
            non_empty_index += 1
        else:
            embeddings.append(None)

    # Prepare documents
    logger.info("Preparing documents for indexing...")
    documents = data_processor.prepare_documents(df, embeddings, es_manager)

    # Create Elasticsearch index and index documents
    logger.info("Creating Elasticsearch index...")
    create_result = es_manager.create_index()
    if not create_result.success:
        raise Exception(f"Failed to create Elasticsearch index: {create_result.message}")

    logger.info("Indexing documents...")
    index_result = es_manager.index_documents(documents)
    if not index_result.success:
        raise Exception(f"Failed to index documents: {index_result.errors}")

    # Success report
    embedding_stats = embedder.get_embedding_stats(embeddings)

    logger.info("Data ingestion completed successfully!")
    logger.info(f"Indexed {index_result.indexed_count} documents")
    logger.info(f"Generated {embedding_stats['successful']}/{embedding_stats['total']} embeddings")


if __name__ == "__main__":
    main()
