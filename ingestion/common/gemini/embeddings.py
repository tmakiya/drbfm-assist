"""Gemini embedding generation utilities."""

import gc
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable

import psutil
from google import genai
from loguru import logger

from .retry import create_retry_decorator
from .vertex_ai import get_vertex_ai_credentials


@dataclass(frozen=True)
class EmbeddingJobConfig:
    model_name: str
    task_type: str
    dimensionality: int
    normalize: bool
    max_workers: int


@dataclass(frozen=True)
class Result:
    index: int
    embedding: list[float]
    error_detail: dict[str, Any] | None


def _init_client(location: str) -> genai.Client:
    get_vertex_ai_credentials(location)
    return genai.Client(vertexai=True, location=location)


def _is_empty_text(text: str) -> bool:
    if not text:
        return True
    return not text.strip()


def _text_preview(text: str, limit: int = 100) -> str:
    text_value = str(text)
    if len(text_value) > limit:
        return text_value[:limit]
    return text_value


def _empty_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "embedded": 0,
        "skipped_empty": 0,
        "errors": 0,
        "skipped_details": [],
        "error_details": [],
    }


def _generate_single_embedding(
    client: genai.Client,
    text: str,
    config: EmbeddingJobConfig,
) -> list[float]:
    """Generate a single embedding with retry logic."""
    retry_decorator = create_retry_decorator(
        operation_name=f"embed_content({config.model_name})",
    )

    @retry_decorator
    def _call():
        result = client.models.embed_content(
            model=config.model_name,
            contents=text,
            config=genai.types.EmbedContentConfig(
                task_type=config.task_type,
                output_dimensionality=config.dimensionality,
            ),
        )
        return result.embeddings[0].values

    return _call()


def _normalize_embedding(embedding: list[float]) -> list[float]:
    """Normalize an embedding vector to unit length."""
    if not embedding:
        return embedding
    norm = math.sqrt(sum(float(x) * float(x) for x in embedding))
    if norm == 0.0:
        return embedding
    return [float(x) / norm for x in embedding]


def _init_metrics() -> tuple[psutil.Process, float]:
    process = psutil.Process()
    initial_memory_mb = process.memory_info().rss / 1024 / 1024
    logger.info(f"Initial memory usage: {initial_memory_mb:.1f} MB")
    return process, initial_memory_mb


def _count_success(embeddings: list[list[float] | None], dimensionality: int) -> int:
    return sum(1 for e in embeddings if e and len(e) == dimensionality)


def _log_progress(
    completed_count: int,
    total: int,
    embeddings: list[list[float] | None],
    dimensionality: int,
    process: psutil.Process,
    initial_memory_mb: float,
) -> None:
    percentage = completed_count * 100 // total
    success_count = _count_success(embeddings, dimensionality)
    current_memory_mb = process.memory_info().rss / 1024 / 1024
    memory_delta_mb = current_memory_mb - initial_memory_mb
    logger.info(
        f"Progress: [{percentage:3d}%] {completed_count:,}/{total:,} embeddings "
        f"({success_count} successful) | "
        f"Memory: {current_memory_mb:.1f} MB (+{memory_delta_mb:.1f} MB)"
    )


def _log_summary(
    embeddings: list[list[float] | None],
    skipped_details: list[dict[str, Any]],
    dimensionality: int,
    workers: int,
    process: psutil.Process,
    initial_memory_mb: float,
) -> int:
    success_count = _count_success(embeddings, dimensionality)
    failed_count = len(embeddings) - success_count
    final_memory_mb = process.memory_info().rss / 1024 / 1024
    memory_delta_mb = final_memory_mb - initial_memory_mb
    logger.info(
        f"Completed: {success_count}/{len(embeddings)} embeddings generated "
        f"({failed_count} failed, skipped_empty={len(skipped_details)}) | "
        f"Workers: {workers} | Dim: {dimensionality} | "
        f"Final Memory: {final_memory_mb:.1f} MB (+{memory_delta_mb:.1f} MB)"
    )
    return success_count


def _process_single_text(
    idx: int,
    text: str,
    client: genai.Client,
    config: EmbeddingJobConfig,
) -> Result:
    task_start = time.time()
    logger.debug(f"[Task {idx}] Starting embedding generation")
    try:
        embedding = _generate_single_embedding(client, text, config)
        elapsed = time.time() - task_start
        logger.debug(f"[Task {idx}] Completed in {elapsed:.1f}s")
        return Result(idx, embedding, None)
    except Exception as e:
        elapsed = time.time() - task_start
        text_preview = _text_preview(text)
        logger.error(
            f"[Task {idx}] Failed after {elapsed:.1f}s and {config.max_retries} retries: "
            f"{str(e)[:200]} | Text preview: {text_preview}"
        )
        return Result(
            idx,
            [],
            {
                "index": idx,
                "reason": "embedding_error",
                "message": str(e)[:200],
                "text_preview": text_preview,
            },
        )


def _iter_results(
    texts: list[str],
    *,
    client: genai.Client,
    config: EmbeddingJobConfig,
) -> Iterable[Result]:
    max_workers = config.max_workers
    if max_workers <= 1:
        for idx, text in enumerate(texts):
            if _is_empty_text(text):
                logger.warning(f"Skipping empty text at index {idx}")
                yield Result(idx, [], {"index": idx, "reason": "empty_text"})
                continue
            yield _process_single_text(idx, text, client, config)
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx: dict[Any, int] = {}
        for idx, text in enumerate(texts):
            if _is_empty_text(text):
                logger.warning(f"Skipping empty text at index {idx}")
                yield Result(idx, [], {"index": idx, "reason": "empty_text"})
                continue
            future_to_idx[executor.submit(_process_single_text, idx, text, client, config)] = idx
        logger.info(f"Submitted {len(future_to_idx)} tasks to {max_workers} workers")
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                yield future.result()
            except Exception as e:
                message = str(e)[:200]
                logger.error(f"[Task {idx}] Unexpected error in future.result(): {message}")
                text_preview = _text_preview(texts[idx])
                yield Result(
                    idx,
                    [],
                    {
                        "index": idx,
                        "reason": "future_error",
                        "message": message,
                        "text_preview": text_preview,
                    },
                )


def _apply_result(
    result: Result,
    embeddings: list[list[float] | None],
    skipped_details: list[dict[str, Any]],
    error_details: list[dict[str, Any]],
) -> None:
    embeddings[result.index] = result.embedding
    if result.error_detail:
        if result.error_detail.get("reason") == "empty_text":
            skipped_details.append(result.error_detail)
        else:
            error_details.append(result.error_detail)


def _fill_missing_results(
    embeddings: list[list[float] | None],
    error_details: list[dict[str, Any]],
) -> None:
    for idx, embedding in enumerate(embeddings):
        if embedding is None:
            logger.warning(f"Task {idx} was not processed, marking as failed")
            embeddings[idx] = []
            error_details.append({"index": idx, "reason": "missing_result"})


def generate_embeddings_batch(
    texts: list[str],
    model_name: str = "gemini-embedding-001",
    location: str = "us-central1",
    task_type: str = "RETRIEVAL_DOCUMENT",
    dimensionality: int = 3072,
    normalize: bool = False,
    max_workers: int = 1,
) -> tuple[list[list[float]], dict[str, Any]]:
    if not texts:
        return [], _empty_summary()

    config = EmbeddingJobConfig(
        model_name=model_name,
        task_type=task_type,
        dimensionality=dimensionality,
        normalize=normalize,
        max_workers=max(1, max_workers),
    )
    client = _init_client(location)

    total = len(texts)

    logger.info(f"Generating embeddings for {total} texts with {config.max_workers} workers...")

    process, initial_memory_mb = _init_metrics()

    embeddings: list[list[float] | None] = [None] * total
    skipped_details: list[dict[str, Any]] = []
    error_details: list[dict[str, Any]] = []
    completed_count = 0

    for result in _iter_results(
        texts,
        client=client,
        config=config,
    ):
        _apply_result(result, embeddings, skipped_details, error_details)
        completed_count += 1
        if completed_count % 10 == 0:
            _log_progress(
                completed_count,
                total,
                embeddings,
                dimensionality,
                process,
                initial_memory_mb,
            )

    _fill_missing_results(embeddings, error_details)
    success_count = _log_summary(
        embeddings,
        skipped_details,
        dimensionality,
        config.max_workers,
        process,
        initial_memory_mb,
    )

    gc.collect()

    if config.normalize:
        embeddings = [_normalize_embedding(emb) for emb in embeddings]
        logger.info("Normalized embeddings to unit length")

    summary = {
        "total": len(embeddings),
        "embedded": success_count,
        "skipped_empty": len(skipped_details),
        "errors": len(error_details),
        "skipped_details": skipped_details,
        "error_details": error_details,
    }
    return embeddings, summary
