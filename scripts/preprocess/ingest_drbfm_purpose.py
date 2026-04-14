#!/usr/bin/env python3
"""Data Ingestion Script for DRBFM Purpose Index

Loads DRBFM data or failure report data from CSV, generates embeddings for change_point field,
and indexes to Elasticsearch for the purpose-based DRBFM search workflow.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import pandas as pd
from dotenv import load_dotenv
from loguru import logger

from drassist.config import ConfigManager
from drassist.elasticsearch import ElasticsearchManager
from drassist.embeddings import AzureOpenAIEmbedder

load_dotenv()


class DrbfmPurposeDataProcessor:
    """DRBFM Purpose CSV data processing and preparation"""

    def __init__(self, config: ConfigManager, data_file: Optional[Path] = None):
        self.config = config
        self.data_file = data_file or Path(config.data["file_path"])

    def load_data(self) -> pd.DataFrame:
        """Load CSV data"""
        if not self.data_file.exists():
            raise FileNotFoundError(f"Data file not found: {self.data_file}")

        df = pd.read_csv(self.data_file, encoding="utf-8")
        logger.info(f"Loaded {len(df)} records from {self.data_file}")

        # Create doc_id from index
        df = df.reset_index()
        df = df.rename(columns={"index": "doc_id"})

        # Fill NaN values with empty strings
        df.fillna("", inplace=True)

        return df

    def prepare_drbfm_documents(
        self, df: pd.DataFrame, embeddings: List[Optional[List[float]]]
    ) -> List[Dict[str, Any]]:
        """Prepare DRBFM documents for Elasticsearch indexing"""
        documents = []

        for idx, row in df.iterrows():
            doc = {
                "doc_id": row["doc_id"],
                "source_file": row.get("source_file", ""),
                "source_type": "DRBFM",
                "source_id": row.get("original_file_id", ""),
                "product": row.get("product", ""),
                "part": row.get("part", ""),
                "change_point": row.get("change_point", ""),
                "function": row.get("function", ""),
                "section": row.get("section", ""),
                "function_category": row.get("function_category", ""),
                "failure_mode": row.get("failure_mode", ""),
                "cause": row.get("cause", ""),
                "effect": row.get("effect", ""),
                "countermeasure": row.get("countermeasure", ""),
            }

            # Add embedding if available
            if embeddings[idx] is not None:
                doc["change_point_embedding"] = embeddings[idx]

            documents.append(doc)

        logger.info(f"Prepared {len(documents)} DRBFM documents for indexing")
        return documents

    def prepare_failure_report_documents(
        self, df: pd.DataFrame, embeddings: List[Optional[List[float]]], start_doc_id: int = 0
    ) -> List[Dict[str, Any]]:
        """Prepare failure report documents for Elasticsearch indexing"""
        documents = []

        for idx, row in df.iterrows():
            doc = {
                "doc_id": start_doc_id + idx,
                "source_file": "",
                "source_type": "品質会議提議内容詳細",
                "source_id": row.get("drawing_id", ""),
                "product": "",
                "part": "",
                "change_point": "",
                "function": "",
                "section": row.get("section", ""),
                "function_category": row.get("function_category", ""),
                "failure_mode": row.get("failure_mode", ""),
                "cause": "",
                "effect": "",
                "countermeasure": "",
            }

            # Add embedding if available (will be None for failure reports as they don't have change_point)
            if idx < len(embeddings) and embeddings[idx] is not None:
                doc["change_point_embedding"] = embeddings[idx]

            documents.append(doc)

        logger.info(f"Prepared {len(documents)} failure report documents for indexing")
        return documents

    def prepare_design_change_documents(
        self, df: pd.DataFrame, embeddings: List[Optional[List[float]]], start_doc_id: int = 0
    ) -> List[Dict[str, Any]]:
        """Prepare design change documents for Elasticsearch indexing"""
        documents = []

        for idx, row in df.iterrows():
            doc = {
                "doc_id": start_doc_id + idx,
                "source_file": "",
                "source_type": "設計変更履歴",
                "source_id": row.get("original_file_id", ""),
                "product": row.get("product", ""),
                "part": "",
                "change_point": "",
                "function": "",
                "section": row.get("section", ""),
                "function_category": row.get("function", ""),
                "failure_mode": row.get("failure_mode", ""),
                "cause": "",
                "effect": "",
                "countermeasure": "",
            }

            # Add embedding if available (will be None for design changes as they don't have change_point)
            if idx < len(embeddings) and embeddings[idx] is not None:
                doc["change_point_embedding"] = embeddings[idx]

            documents.append(doc)

        logger.info(f"Prepared {len(documents)} design change documents for indexing")
        return documents


def generate_embeddings_for_texts(
    embedder: AzureOpenAIEmbedder, texts: List[str]
) -> List[Optional[List[float]]]:
    """Generate embeddings for a list of texts"""
    # Filter out empty strings and replace with None to skip embedding generation
    processed_texts = []
    for text in texts:
        if text and str(text).strip():
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

    return embeddings


@click.command()
@click.option(
    "--config-path",
    type=click.Path(exists=True, dir_okay=False),
    default="configs/drbfm_purpose.yaml",
    help="Path to configuration file",
)
@click.option(
    "--source-type",
    type=click.Choice(["drbfm", "failure", "design_change", "both", "all"]),
    default="both",
    help="Type of data to ingest: drbfm, failure, design_change, both (drbfm+failure), or all",
)
@click.option(
    "--drbfm-file",
    type=click.Path(exists=True, dir_okay=False),
    default="data/purpose/DRBFM/purpose_DRBFM_structured_20251204.csv",
    help="Path to DRBFM CSV file",
)
@click.option(
    "--failure-file",
    type=click.Path(exists=True, dir_okay=False),
    default="data/purpose/failure_reports/failure_report_strcutured_v1.csv",
    help="Path to failure report CSV file",
)
@click.option(
    "--design-change-file",
    type=click.Path(exists=True, dir_okay=False),
    default="data/purpose/design_changes/design_changes_attributes.csv",
    help="Path to design change CSV file",
)
@click.option(
    "--delete-index",
    is_flag=True,
    default=False,
    help="Delete existing index before ingesting",
)
def main(config_path: str, source_type: str, drbfm_file: str, failure_file: str, design_change_file: str, delete_index: bool):
    """Ingest DRBFM Purpose data into Elasticsearch"""
    logger.info("Starting DRBFM Purpose data ingestion process")
    logger.info(f"Source type: {source_type}")

    # Initialize configuration
    config = ConfigManager(config_path)
    logger.info("Configuration loaded successfully")

    # Initialize components
    embedder = AzureOpenAIEmbedder(config)
    es_manager = ElasticsearchManager(config)

    # Delete index if requested
    if delete_index:
        logger.info("Deleting existing index...")
        es_manager.delete_index()

    # Create Elasticsearch index
    logger.info("Creating Elasticsearch index...")
    create_result = es_manager.create_index()
    if not create_result.success:
        raise Exception(f"Failed to create Elasticsearch index: {create_result.message}")

    all_embeddings = []
    total_indexed = 0

    # Ingest DRBFM data
    if source_type in ["drbfm", "both", "all"]:
        logger.info("Processing DRBFM data...")
        drbfm_path = Path(drbfm_file)
        data_processor = DrbfmPurposeDataProcessor(config, drbfm_path)

        # Load data
        df = data_processor.load_data()

        # Generate embeddings for change_point field
        logger.info("Generating embeddings for change_point field...")
        change_point_texts = df["change_point"].tolist()
        embeddings = generate_embeddings_for_texts(embedder, change_point_texts)
        all_embeddings.extend(embeddings)

        # Prepare documents
        logger.info("Preparing DRBFM documents for indexing...")
        documents = data_processor.prepare_drbfm_documents(df, embeddings)

        # Index documents
        logger.info("Indexing DRBFM documents...")
        index_result = es_manager.index_documents(documents)
        if not index_result.success:
            raise Exception(f"Failed to index DRBFM documents: {index_result.errors}")
        total_indexed += index_result.indexed_count
        logger.info(f"Indexed {index_result.indexed_count} DRBFM documents")

    # Ingest failure report data
    if source_type in ["failure", "both", "all"]:
        logger.info("Processing failure report data...")
        failure_path = Path(failure_file)
        data_processor = DrbfmPurposeDataProcessor(config, failure_path)

        # Load data
        df = data_processor.load_data()

        # Failure reports don't have change_point, so we create empty embeddings
        embeddings = [None] * len(df)

        # Prepare documents (start doc_id from a high number to avoid conflicts)
        logger.info("Preparing failure report documents for indexing...")
        start_doc_id = 100000  # Start from a high number to avoid conflicts with DRBFM docs
        documents = data_processor.prepare_failure_report_documents(df, embeddings, start_doc_id)

        # Index documents
        logger.info("Indexing failure report documents...")
        index_result = es_manager.index_documents(documents)
        if not index_result.success:
            raise Exception(f"Failed to index failure report documents: {index_result.errors}")
        total_indexed += index_result.indexed_count
        logger.info(f"Indexed {index_result.indexed_count} failure report documents")

    # Ingest design change data
    if source_type in ["design_change", "all"]:
        logger.info("Processing design change data...")
        design_change_path = Path(design_change_file)
        data_processor = DrbfmPurposeDataProcessor(config, design_change_path)

        # Load data
        df = data_processor.load_data()

        # Design changes don't have change_point, so we create empty embeddings
        embeddings = [None] * len(df)

        # Prepare documents (start doc_id from 200000 to avoid conflicts)
        logger.info("Preparing design change documents for indexing...")
        start_doc_id = 200000  # Start from 200000 to avoid conflicts with DRBFM and failure report docs
        documents = data_processor.prepare_design_change_documents(df, embeddings, start_doc_id)

        # Index documents
        logger.info("Indexing design change documents...")
        index_result = es_manager.index_documents(documents)
        if not index_result.success:
            raise Exception(f"Failed to index design change documents: {index_result.errors}")
        total_indexed += index_result.indexed_count
        logger.info(f"Indexed {index_result.indexed_count} design change documents")

    # Success report
    embedding_stats = embedder.get_embedding_stats(all_embeddings) if all_embeddings else {"successful": 0, "total": 0}

    logger.info("Data ingestion completed successfully!")
    logger.info(f"Total indexed: {total_indexed} documents")
    logger.info(f"Generated {embedding_stats['successful']}/{embedding_stats['total']} embeddings")


if __name__ == "__main__":
    main()
