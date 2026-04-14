"""LLM execution and recovery helpers for PFMEA mapping jobs (async version)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from src.common.concurrency import ParallelExecutionError
from src.common.perf import time_block
from src.services.circuit_breaker import get_global_breaker
from src.services.llm_executor import LLMExecutor
from src.services.llm_metrics import get_llm_metrics
from src.services.llm_retry_policies import RetryPolicies

from .function_mapper import (
    PLACEHOLDER_REASON,
    FunctionMappingError,
    FunctionMappingRecord,
    FunctionMappingRequest,
    FunctionMappingResponse,
    MalformedMappingResponseError,
    amap_functions_to_requirements,
)
from .mapping_context import MappingContext
from .mapping_jobs import MappingJob

logger = logging.getLogger(__name__)

# Unified retry policies from llm_retry_policies.py
_RATE_LIMIT_POLICY = RetryPolicies.RATE_LIMITED
_MALFORMED_POLICY = RetryPolicies.MALFORMED_RECOVERY
MALFORMED_CHUNK_INITIAL_SIZE = 6
ASSURANCE_INDEX_RETRY_ATTEMPTS = 2
ASSURANCE_INDEX_ERROR_NOTE = (
    "製造保証項目のインデックスが欠落したため自動補正を適用しました。"
)

# Threshold for warning about missing requirements
MISSING_REQUIREMENT_ALERT_THRESHOLD = 0.20  # 20%


def _check_mapping_completeness(
    response: FunctionMappingResponse,
    total_requirements: int,
) -> None:
    """Check mapping completeness and warn if missing rate exceeds threshold."""
    if total_requirements == 0:
        return

    # Count records with placeholder reason as missing
    missing_count = sum(
        1
        for r in response.records
        if r.reason == PLACEHOLDER_REASON or r.function_index == 0
    )

    # Also count explicit missing indices
    missing_count = max(missing_count, len(response.missing_requirement_indices))

    ratio = missing_count / total_requirements
    if ratio > MISSING_REQUIREMENT_ALERT_THRESHOLD:
        logger.warning(
            "網羅性警告: %d/%d (%.1f%%) の要求事項が未割当です。"
            "LLM応答の品質を確認してください。",
            missing_count,
            total_requirements,
            ratio * 100,
        )


async def aexecute_mapping_job(
    executor: LLMExecutor,
    job: MappingJob,
) -> FunctionMappingResponse:
    """非同期版マッピングジョブ実行。"""
    total_requirements = len(job.request.requirements)

    with time_block(
        "pfmea.mapping.request",
        metadata={"phase": "pfmea", "requirements": total_requirements},
    ):
        try:
            base_response = await _arun_mapping_with_rate_limit_retry(
                executor, job.request, job.context
            )
        except MalformedMappingResponseError as exc:
            logger.warning(
                "PFMEA function mapping base応答が不正だったためチャンク処理へフォールバックします。"
                "requirements=%d, error=%s",
                total_requirements,
                exc,
            )
            result = await _arecover_from_malformed_response(
                executor, job.request, job.context, cause=exc
            )
            _check_mapping_completeness(result, total_requirements)
            return result

    if not base_response.missing_requirement_indices:
        _check_mapping_completeness(base_response, total_requirements)
        return base_response

    result = await _arecover_missing_requirements(
        executor, job.request, job.context, base_response
    )
    _check_mapping_completeness(result, total_requirements)
    return result


def handle_parallel_error(exc: ParallelExecutionError) -> None:
    """Handle errors from parallel execution."""
    job = exc.item
    cause = exc.__cause__ or exc

    if isinstance(cause, FunctionMappingError):
        raise cause

    if isinstance(job, MappingJob):
        raise FunctionMappingError(
            f"工程マッピング処理でエラーが発生しました（change_id={job.change_id}, "
            f"process={job.process_key}）: {cause}"
        ) from cause

    raise FunctionMappingError(
        "工程マッピングの並列実行で予期しないエラーが発生しました。"
    ) from cause


async def _arun_mapping_with_rate_limit_retry(
    executor: LLMExecutor,
    request: FunctionMappingRequest,
    context: MappingContext,
) -> FunctionMappingResponse:
    """非同期版レートリミットリトライ付きマッピング実行。"""
    last_error: FunctionMappingError | None = None
    malformed_attempts = 0
    assurance_failures = 0

    for attempt in range(1, _RATE_LIMIT_POLICY.max_attempts + 1):
        try:
            retry_context = context.with_retry(attempt=attempt, method="retry")

            response = await amap_functions_to_requirements(
                executor.model,
                request,
                executor=executor,
                context=retry_context,
            )

            # Record success to Circuit Breaker
            get_global_breaker().record_success()

            retries = attempt - 1
            if retries != response.rate_limit_retries:
                response = replace(response, rate_limit_retries=retries)

            return response

        except MalformedMappingResponseError as exc:
            malformed_attempts += 1
            last_error = exc

            operation_name = getattr(
                executor, "_operation_name", "llm_function_mapping"
            )
            get_llm_metrics().record_malformed_response(
                operation_name,
                attempt=malformed_attempts,
                message=str(exc),
            )

            logger.warning(
                "PFMEA function mapping JSON解析失敗のため再試行します "
                "(attempt=%d/%d, preview=%s)。",
                malformed_attempts,
                _MALFORMED_POLICY.max_attempts,
                exc.raw_text[:80].replace("\n", "\\n"),
            )

            if malformed_attempts >= _MALFORMED_POLICY.max_attempts:
                raise

            await asyncio.sleep(_MALFORMED_POLICY.base_delay)
            continue

        except FunctionMappingError as exc:
            message = str(exc)
            is_rate_limit = _is_rate_limit_error(message)

            # Record failure to Circuit Breaker
            get_global_breaker().record_failure(
                is_rate_limit=is_rate_limit,
                message=message,
            )

            if _is_assurance_index_error(message):
                assurance_failures += 1
                logger.warning(
                    "PFMEA function mapping assurance_index error detected "
                    "(attempt=%d/%d): %s",
                    assurance_failures,
                    ASSURANCE_INDEX_RETRY_ATTEMPTS,
                    message,
                )

                if assurance_failures < ASSURANCE_INDEX_RETRY_ATTEMPTS:
                    continue

                logger.error(
                    "PFMEA function mapping assurance_index error persisted after %d attempts. "
                    "Returning placeholder results.",
                    assurance_failures,
                )

                return _build_assurance_error_response(request, message)

            if not is_rate_limit or attempt == _RATE_LIMIT_POLICY.max_attempts:
                raise

            last_error = exc
            delay = _RATE_LIMIT_POLICY.base_delay * (
                _RATE_LIMIT_POLICY.multiplier ** (attempt - 1)
            )
            sleep_time = delay + _random_jitter(_RATE_LIMIT_POLICY.jitter)

            get_llm_metrics().record_rate_limit(
                "llm_function_mapping",
                attempt=attempt,
                message=message,
            )

            logger.warning(
                "PFMEA function mapping rate limit detected (attempt=%d/%d). "
                "Retrying in %.2fs.",
                attempt,
                _RATE_LIMIT_POLICY.max_attempts,
                sleep_time,
            )

            await asyncio.sleep(sleep_time)

    if last_error is not None:
        raise last_error

    raise FunctionMappingError("PFMEA function mapping failed without error detail.")


async def _arecover_from_malformed_response(
    executor: LLMExecutor,
    request: FunctionMappingRequest,
    context: MappingContext,
    *,
    cause: MalformedMappingResponseError,
) -> FunctionMappingResponse:
    """非同期版マルフォームレスポンスからのリカバリー。"""
    requirements = request.requirements
    total = len(requirements)
    chunk_size = MALFORMED_CHUNK_INITIAL_SIZE

    all_records: list[FunctionMappingRecord] = []
    for start in range(0, total, chunk_size):
        end = min(start + chunk_size, total)
        chunk_requirements = requirements[start:end]

        chunk_request = FunctionMappingRequest(
            functions=request.functions,
            assurances=request.assurances,
            requirements=chunk_requirements,
            extra=f"Chunk {start + 1}-{end} of {total}",
        )

        chunk_context = context.with_chunk(
            chunk_size=chunk_size,
            chunk_index=start // chunk_size,
            total_chunks=(total + chunk_size - 1) // chunk_size,
        )

        try:
            chunk_response = await amap_functions_to_requirements(
                executor.model,
                chunk_request,
                executor=executor,
                context=chunk_context,
            )

            for record in chunk_response.records:
                adjusted_record = FunctionMappingRecord(
                    function_index=record.function_index,
                    assurance_index=record.assurance_index,
                    requirement_index=start + record.requirement_index,
                    function=record.function,
                    assurance=record.assurance,
                    requirement=record.requirement,
                    reason=record.reason,
                )
                all_records.append(adjusted_record)

        except Exception:
            for i, req in enumerate(chunk_requirements, start=1):
                all_records.append(
                    FunctionMappingRecord(
                        function_index=0,
                        assurance_index=0,
                        requirement_index=start + i,
                        function="",
                        assurance="",
                        requirement=str(req),
                        reason=f"{PLACEHOLDER_REASON} (Chunk processing failed)",
                    )
                )

    return FunctionMappingResponse(
        records=tuple(all_records),
        raw_text=f"Recovered via chunking (chunk_size={chunk_size})",
        missing_requirement_indices=(),
        recovery_attempts=1,
        errors=(f"Original error: {cause}",),
    )


async def _arecover_missing_requirements(
    executor: LLMExecutor,
    request: FunctionMappingRequest,
    context: MappingContext,
    base_response: FunctionMappingResponse,
) -> FunctionMappingResponse:
    """非同期版欠落要求事項のリカバリー。"""
    if not base_response.missing_requirement_indices:
        return base_response

    missing_requirements: list[str] = []
    for idx in base_response.missing_requirement_indices:
        if 1 <= idx <= len(request.requirements):
            missing_requirements.append(request.requirements[idx - 1])

    if not missing_requirements:
        return base_response

    retry_request = FunctionMappingRequest(
        functions=request.functions,
        assurances=request.assurances,
        requirements=tuple(missing_requirements),
        extra=f"未割当だった要求事項の再処理 (indices: {base_response.missing_requirement_indices})",
    )

    retry_context = context.with_retry(attempt=2, method="missing_recovery")

    try:
        retry_response = await amap_functions_to_requirements(
            executor.model,
            retry_request,
            executor=executor,
            context=retry_context,
        )

        records = list(base_response.records)
        for i, retry_record in enumerate(retry_response.records):
            if i < len(base_response.missing_requirement_indices):
                original_idx = base_response.missing_requirement_indices[i]
                for j, record in enumerate(records):
                    if record.requirement_index == original_idx:
                        records[j] = FunctionMappingRecord(
                            function_index=retry_record.function_index,
                            assurance_index=retry_record.assurance_index,
                            requirement_index=original_idx,
                            function=retry_record.function,
                            assurance=retry_record.assurance,
                            requirement=retry_record.requirement,
                            reason=retry_record.reason,
                        )
                        break

        return FunctionMappingResponse(
            records=tuple(records),
            raw_text=base_response.raw_text + "\n" + retry_response.raw_text,
            missing_requirement_indices=(),
            recovery_attempts=1,
            rate_limit_retries=base_response.rate_limit_retries,
        )
    except Exception:
        return base_response


def _is_rate_limit_error(message: str) -> bool:
    return LLMExecutor.is_rate_limit_message(message)


def _is_assurance_index_error(message: str) -> bool:
    return "assurance_index" in message


def _build_assurance_error_response(
    request: FunctionMappingRequest, message: str
) -> FunctionMappingResponse:
    records: list[FunctionMappingRecord] = []
    reason_suffix = f"{ASSURANCE_INDEX_ERROR_NOTE} (詳細: {message})".strip()

    for idx, requirement in enumerate(request.requirements, start=1):
        requirement_text = str(requirement).strip()
        reason = (
            f"{PLACEHOLDER_REASON} {reason_suffix}"
            if reason_suffix
            else PLACEHOLDER_REASON
        )
        records.append(
            FunctionMappingRecord(
                function_index=0,
                assurance_index=0,
                requirement_index=idx,
                function="",
                assurance="",
                requirement=requirement_text,
                reason=reason.strip(),
            )
        )

    return FunctionMappingResponse(
        records=tuple(records),
        raw_text="",
        missing_requirement_indices=(),
        errors=(message,),
    )


def _random_jitter(bound: float) -> float:
    try:
        import random

        return random.uniform(0, bound)
    except Exception:
        return 0.0


__all__ = ["aexecute_mapping_job", "handle_parallel_error"]
