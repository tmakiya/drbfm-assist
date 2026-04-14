"""Cleaner version of PFMEA mapping runtime using Context Object pattern.

This module orchestrates the PFMEA function mapping process with improved
parameter handling and cleaner architecture.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

from src.common.concurrency import ParallelExecutionError, parallel_map
from src.common.perf import record_event, time_block
from src.services.circuit_breaker import (
    AdaptiveConcurrencyLimiter,
    CircuitOpenError,
    get_global_breaker,
)
from src.services.llm_executor import LLMExecutor
from src.services.llm_metrics import metrics_enabled
from src.services.pfmea_context import PfmeaContext

from .function_mapper import (
    FunctionMappingError,
    FunctionMappingResponse,
    serialize_records,
)
from .mapping_cache_coordinator import MappingCacheCoordinator
from .mapping_execution import execute_mapping_job, handle_parallel_error
from .mapping_jobs import MappingJob, build_mapping_jobs
from .mapping_logger import get_mapping_logger
from .mapping_results import apply_records_to_dataframe

logger = logging.getLogger(__name__)

DEFAULT_MAPPING_WORKERS = 20


def ensure_function_mappings(
    session_manager: Any,
    contexts: Mapping[str, PfmeaContext | None],
    *,
    model: Any,
    progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> None:
    """Ensure PFMEA contexts have function⇔requirement mappings.

    This is the main entry point for the mapping process with cleaner architecture.
    """
    start_time = time.perf_counter()

    # Initialize logger session
    mapping_logger = get_mapping_logger()
    mapping_logger.set_session_info(
        session_id=time.strftime("%Y%m%d_%H%M%S"),
        model_name=str(model) if model else "unknown",
    )

    coordinator = MappingCacheCoordinator(session_manager)

    try:
        build_result = build_mapping_jobs(
            contexts,
            cache_fetcher=coordinator.fetch,
            model=model,
        )
        jobs = build_result.jobs
        mapping_results = build_result.mapping_results

        # Report start
        if progress is not None:
            progress({"event": "start", "total": len(jobs), "stage": "mapping"})

        # Process jobs in parallel
        if jobs:
            _process_jobs_parallel(
                jobs,
                model,
                mapping_results,
                coordinator.update_caches,
                progress,
            )

        # Save results
        coordinator.store_results(mapping_results)

        # Report statistics
        total_requests = (
            build_result.session_cache_hits
            + build_result.persistent_cache_hits
            + len(jobs)
        )
        if progress is not None:
            progress(
                {
                    "event": "complete",
                    "stage": "mapping",
                    "total": len(jobs),
                    "session_cache_hits": build_result.session_cache_hits,
                    "persistent_cache_hits": build_result.persistent_cache_hits,
                    "requests": total_requests,
                }
            )

        # Log summary
        log_stats = mapping_logger.get_summary_statistics()
        if log_stats["total_corrections"] > 0:
            logger.info(
                "PFMEA mapping completed with %d index corrections. "
                "By field: %s, By type: %s",
                log_stats["total_corrections"],
                log_stats["by_field"],
                log_stats["by_correction_type"],
            )

            coordinator.store_logs(mapping_logger.get_logs_as_dataframe())

        if metrics_enabled():
            record_event(
                "pfmea.ensure_function_mappings",
                start=start_time,
                end=time.perf_counter(),
                metadata={
                    "phase": "pfmea",
                    "jobs": len(jobs),
                    "session_cache_hits": build_result.session_cache_hits,
                    "persistent_cache_hits": build_result.persistent_cache_hits,
                    "requests": total_requests,
                    "contexts": len(contexts),
                },
            )

    finally:
        coordinator.close()


def _process_jobs_parallel(
    jobs: list[MappingJob],
    model: Any,
    mapping_results: dict[str, dict[str, dict[str, Any]]],
    cache_updater: Callable[[str, Mapping[str, Any]], None],
    progress: Callable[[Mapping[str, Any]], None] | None,
) -> None:
    """Process mapping jobs in parallel with Circuit Breaker protection."""
    # Get adaptive concurrency based on Circuit Breaker state
    breaker = get_global_breaker()
    limiter = AdaptiveConcurrencyLimiter(breaker, base_workers=DEFAULT_MAPPING_WORKERS)
    effective_workers = limiter.get_effective_max_workers()

    logger.debug(
        "PFMEA function mapping executing %d jobs in parallel "
        "(effective_workers=%d, base=%d, breaker_state=%s)",
        len(jobs),
        effective_workers,
        DEFAULT_MAPPING_WORKERS,
        breaker.get_state().value,
    )

    # Check if circuit is open before starting
    try:
        breaker.check_can_proceed()
    except CircuitOpenError as exc:
        logger.warning(
            "Circuit Breaker is OPEN, delaying mapping execution. Will retry in %.1fs",
            exc.time_until_half_open,
        )
        raise FunctionMappingError(
            f"LLM サービスが一時的に利用できません（レート制限中）。"
            f"{exc.time_until_half_open:.0f}秒後に再試行してください。"
        ) from exc

    executor = LLMExecutor(model, operation_name="llm_function_mapping")

    try:
        with time_block(
            "pfmea.mapping.parallel",
            metadata={
                "phase": "pfmea",
                "jobs": len(jobs),
                "max_workers": effective_workers,
                "breaker_state": breaker.get_state().value,
            },
        ):
            job_results = parallel_map(
                lambda job: (job, execute_mapping_job(executor, job)),
                jobs,
                max_workers=effective_workers,
            )
    except ParallelExecutionError as exc:
        handle_parallel_error(exc)

    # Apply results
    with time_block(
        "pfmea.mapping.apply_results",
        metadata={"phase": "pfmea", "jobs": len(job_results)},
    ):
        for index, (job, response) in enumerate(job_results, start=1):
            _apply_job_result(
                job,
                response,
                mapping_results,
                cache_updater,
                progress,
                index,
                len(job_results),
            )


def _apply_job_result(
    job: MappingJob,
    response: FunctionMappingResponse,
    mapping_results: dict[str, dict[str, dict[str, Any]]],
    cache_updater: Callable[[str, Mapping[str, Any]], None],
    progress: Callable[[Mapping[str, Any]], None] | None,
    index: int,
    total: int,
) -> None:
    """Apply a single job result."""
    records = response.records

    if len(records) != len(job.requirement_indices):
        raise FunctionMappingError(
            f"マッピング結果の行数が要求事項数と一致しません（{len(records)} != {len(job.requirement_indices)}）。"
        )

    if response.missing_requirement_indices:
        logger.warning(
            "PFMEA function mapping returned unmatched requirements "
            "(change_id=%s, process=%s, indices=%s)",
            job.change_id,
            job.process_key,
            response.missing_requirement_indices,
        )

    apply_records_to_dataframe(job.dataframe, job.requirement_indices, records)

    if response.errors:
        if "mapping_error" not in job.dataframe.columns:
            job.dataframe["mapping_error"] = ""
        job.dataframe.at[job.requirement_indices[0], "mapping_error"] = response.errors[
            0
        ]

    # Save results
    serialized = serialize_records(records)
    mapping_results.setdefault(job.change_id, {})[job.process_key] = {
        "signature": job.signature,
        "records": serialized,
        "raw_text": response.raw_text,
        "errors": list(response.errors),
    }

    # Update caches
    cache_payload = {
        "records": serialized,
        "raw_text": response.raw_text,
    }
    if response.errors:
        cache_payload["errors"] = list(response.errors)

    cache_updater(job.signature, cache_payload)

    # Report progress
    if progress is not None:
        progress(
            {
                "event": "job_completed",
                "stage": "mapping",
                "change_id": job.change_id,
                "process_key": job.process_key,
                "completed": index,
                "total": total,
                "missing": len(response.missing_requirement_indices),
                "recovery_attempts": response.recovery_attempts,
                "rate_limit_retries": response.rate_limit_retries,
            }
        )


__all__ = ["ensure_function_mappings"]
