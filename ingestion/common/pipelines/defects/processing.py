"""Defect processing utilities for analyzing images with Gemini."""

import json
import threading
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl
from loguru import logger

from common.gemini import GeminiClient, analyze_images_with_structured_output, generate_embeddings_batch
from common.gemini.analysis_parallel import run_parallel

from .config import EmbeddingConfig, ImageAnalysisConfig


def _process_single_group(
    group: Dict[str, Any],
    system_instruction: str,
    response_schema: Dict[str, Any],
    model_name: str,
    client: Optional[GeminiClient] = None,
) -> Dict[str, Any]:
    """Process a single original_id group of images.

    Args:
        group: Dictionary containing original_id, image_paths, drawing_ids, page_count
        system_instruction: System instruction for Gemini analysis
        response_schema: Response schema for structured output
        model_name: Gemini model name to use
        client: Optional GeminiClient instance to reuse

    Returns:
        Dictionary with analysis results and metadata

    """
    # Get worker thread information
    worker_id = threading.current_thread().name

    original_id = group["original_id"]
    image_paths = group["image_paths"]
    drawing_ids = group["drawing_ids"]

    # Check total file size (50MB limit)
    MAX_SIZE = 50 * 1024 * 1024  # 50MB
    total_size = sum(path.stat().st_size for path in image_paths)

    # Create default result
    default_result = {
        "original_id": str(original_id),
        "drawing_ids": drawing_ids,
        "page_count": len(image_paths),
        "total_size": total_size,
        "status": "pending",
        "error_detail": "",
    }
    if total_size > MAX_SIZE:
        logger.warning(
            f"[Worker: {worker_id}] Original ID {original_id} total size "
            f"({total_size} bytes) exceeds 50MB limit. Skipping."
        )
        default_result["status"] = "skipped_large_file"
        default_result["error_detail"] = f"Total file size {total_size} bytes exceeds 50MB limit"
        return default_result

    try:
        # Analyze images with Gemini
        success_result = analyze_images_with_structured_output(
            image_paths=image_paths,
            system_instruction=system_instruction,
            response_schema=response_schema,
            model_name=model_name,
            client=client,
        )

        # Add metadata
        success_result["original_id"] = str(original_id)
        success_result["drawing_ids"] = drawing_ids
        success_result["page_count"] = len(image_paths)
        success_result["total_size"] = total_size
        success_result["status"] = "success"
        success_result["error_detail"] = ""

        logger.info(
            f"[Worker: {worker_id}] Successfully processed original_id {original_id}",
            f"({len(image_paths)} images)",
        )
        return success_result

    except Exception as e:
        logger.error(f"[Worker: {worker_id}] Failed to process original_id {original_id}: {e}")
        # For RetryError, use the original cause
        error_detail = str(e.__cause__) if e.__cause__ else str(e)
        default_result["status"] = "image_analysis_error"
        default_result["error_detail"] = error_detail
        return default_result


def group_drawings_by_original_id(drawing_df: pl.DataFrame) -> List[Dict[str, Any]]:
    """Group drawings by original_id for Gemini analysis.

    Args:
        drawing_df: DataFrame with drawing metadata including original_id, page_number, local_path

    Returns:
        List of dictionaries, each containing grouped images for an original_id

    """
    groups = []

    # Debug: Check DataFrame structure
    logger.debug(f"DataFrame columns: {drawing_df.columns}")
    logger.debug(f"DataFrame shape: {drawing_df.shape}")

    # Group by original_id and sort by page_number
    for (original_id,), group_df in drawing_df.sort("page_number").group_by(
        "original_id", maintain_order=True
    ):
        image_paths: list[Path] = []
        drawing_ids: list[str] = []

        for row in group_df.iter_rows(named=True):
            drawing_id = row["drawing_id"]
            # local_path is stored as string in DataFrame
            image_path = Path(row["local_path"])

            if image_path.exists():
                image_paths.append(image_path)
                drawing_ids.append(drawing_id)
            else:
                logger.warning(f"Image file not found: {image_path}")

        if image_paths:
            groups.append(
                {
                    "original_id": original_id,
                    "image_paths": image_paths,
                    "drawing_ids": drawing_ids,
                    "page_count": len(image_paths),
                }
            )

    logger.info(f"Created {len(groups)} original_id groups")
    return groups


def analyze_groups_parallel(
    groups: List[Dict[str, Any]], image_analysis_config: ImageAnalysisConfig
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Analyze image groups in parallel using ThreadPoolExecutor.

    Args:
        groups: List of image groups to process
        image_analysis_config: Configuration for image analysis

    Returns:
        Tuple of (DataFrame of successful records, summary dictionary)

    """
    gemini_client = GeminiClient(model_name=image_analysis_config.model)

    # Create partial function with pre-bound parameters
    process_with_params = partial(
        _process_single_group,
        system_instruction=image_analysis_config.system_instruction,
        response_schema=image_analysis_config.response_schema,
        model_name=image_analysis_config.model,
        client=gemini_client,
    )

    results, errors = run_parallel(
        work_items=groups,
        worker=process_with_params,
        max_workers=image_analysis_config.max_workers,
        log_every=10,
        item_label="groups",
        on_error=_build_error_result,
    )
    if errors:
        failed_ids = []
        for error in errors:
            idx = error.get("index")
            if isinstance(idx, int) and 0 <= idx < len(groups):
                failed_ids.append(str(groups[idx].get("original_id", "")))
        logger.error(f"Failed to process original_id: {failed_ids}")

    success_records = [
        _create_record_from_result(result) for result in results if result.get("status") == "success"
    ]
    success_df = pl.DataFrame(success_records) if success_records else pl.DataFrame()

    summary = {
        "success": sum(1 for r in results if r.get("status") == "success"),
        "skipped_large_file": sum(1 for r in results if r.get("status") == "skipped_large_file"),
        "image_analysis_error": sum(1 for r in results if r.get("status") == "image_analysis_error"),
        "total_groups": len(groups),
    }

    skipped_large_file_ids = [
        str(r.get("original_id", "")) for r in results if r.get("status") == "skipped_large_file"
    ]
    if skipped_large_file_ids:
        logger.warning(f"Skipped original_id (large file): {skipped_large_file_ids}")

    image_error_ids = [
        str(r.get("original_id", "")) for r in results if r.get("status") == "image_analysis_error"
    ]
    if image_error_ids:
        logger.error(f"Image analysis errors for original_id: {image_error_ids}")

    return success_df, summary


def _build_error_result(group: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
    error_detail = str(exc.__cause__) if exc.__cause__ else str(exc)
    return {
        "original_id": str(group.get("original_id", "")),
        "drawing_ids": group.get("drawing_ids", []),
        "page_count": group.get("page_count", 0),
        "total_size": group.get("total_size", 0),
        "status": "image_analysis_error",
        "error_detail": error_detail,
    }


def _create_record_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Create a data record from defect analysis result."""
    original_id = str(result.get("original_id", ""))
    return {
        "original_id": original_id,
        "drawing_ids": result.get("drawing_ids", []),
        "page_count": result.get("page_count", 0),
        "total_size": result.get("total_size", 0),
        "cause_original": result.get("cause_original", ""),
        "cause_unit": result.get("cause_unit", ""),
        "cause_part": result.get("cause_part", []),
        "unit_part_change": result.get("unit_part_change", ""),
        "failure_mode": result.get("failure_mode", ""),
        "failure_effect": result.get("failure_effect", ""),
        "countermeasures": result.get("countermeasures", ""),
    }


def build_dataframe_with_embeddings(
    df: pl.DataFrame,
    embedding_config: EmbeddingConfig,
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Build DataFrame with embeddings from defect analysis results.

    Args:
        df: DataFrame built from successful analysis results
        embedding_config: Configuration for embedding generation

    Returns:
        Tuple of (DataFrame with embeddings, summary dictionary)

    """
    total_records = len(df)
    if df.is_empty():
        logger.warning("No successful results to process")
        return pl.DataFrame(), {
            "embedded": 0,
            "embedding_error": 0,
            "embedding_skipped_empty": 0,
            "total_records": 0,
        }

    logger.info(f"Created DataFrame with {len(df)} records")
    texts = df[embedding_config.source_field].to_list()
    empty_text_skipped = sum(1 for text in texts if not text or (isinstance(text, str) and not text.strip()))

    def _log_rows(details: list[dict[str, Any]], label: str, log_fn) -> None:
        indices = [
            detail.get("index")
            for detail in details
            if isinstance(detail, dict) and isinstance(detail.get("index"), int)
        ]
        indices = sorted({idx for idx in indices if 0 <= idx < len(df)})
        if not indices:
            return
        try:
            rows = [df.row(idx, named=True) for idx in indices]
            log_fn(f"{label} count: {len(rows)}")
            json_str = json.dumps(rows, indent=2, ensure_ascii=False)
            log_fn(f"log:\n{json_str}")
            return
        except Exception as exc:
            log_fn(f"{label} indices: {indices} (failed to extract rows: {exc})")
            return

    # Generate embeddings with error handling
    try:
        embeddings, embedding_summary = generate_embeddings_batch(
            texts=texts,
            model_name=embedding_config.model,
            task_type=embedding_config.task_type,
            dimensionality=embedding_config.dimensionality,
        )

        # Convert empty lists to None (for empty source field)
        embeddings = [emb if emb and len(emb) > 0 else None for emb in embeddings]
        df = df.with_columns(pl.Series("embedding", embeddings))

        logger.info(f"Generated {embedding_summary.get('embedded', 0)}/{len(embeddings)} embeddings")
        _log_rows(embedding_summary.get("skipped_details", []), "Embedding skipped rows", logger.warning)
        _log_rows(embedding_summary.get("error_details", []), "Embedding error rows", logger.error)

    except Exception as e:
        error_detail = str(e.__cause__) if e.__cause__ else str(e)
        logger.error(f"Failed to generate embeddings: {error_detail}")
        if not df.is_empty():
            logger.error(f"Embedding failed rows:\n{df}")
        df = pl.DataFrame()
        embedding_summary = {
            "embedded": 0,
            "skipped_empty": empty_text_skipped,
            "errors": total_records,
        }

    summary = {
        "embedded": embedding_summary.get("embedded", 0),
        "embedding_skipped_empty": embedding_summary.get("skipped_empty", 0),
        "embedding_error": embedding_summary.get("errors", 0),
        "total_records": total_records,
    }

    return df, summary
