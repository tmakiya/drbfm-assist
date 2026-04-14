"""Job construction utilities for PFMEA mapping runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from src.services.pfmea_context import PfmeaContext

from .function_mapper import (
    FunctionMappingRequest,
    build_request_signature,
    serialize_records,
)
from .mapping_context import MappingContext
from .mapping_results import apply_cached_mapping


@dataclass(frozen=True)
class MappingJob:
    change_id: str
    process_key: str
    dataframe: pd.DataFrame
    requirement_indices: list[int]
    request: FunctionMappingRequest
    signature: str
    context: MappingContext


@dataclass(frozen=True)
class JobBuildResult:
    jobs: list[MappingJob]
    mapping_results: dict[str, dict[str, dict[str, Any]]]
    session_cache_hits: int
    persistent_cache_hits: int


def build_mapping_jobs(
    contexts: Mapping[str, PfmeaContext | None],
    *,
    cache_fetcher: Callable[[str], tuple[Mapping[str, Any] | None, str | None]],
    model: Any,
) -> JobBuildResult:
    """Build mapping jobs and reuse cached payloads when possible."""
    mapping_results: dict[str, dict[str, dict[str, Any]]] = {}
    jobs: list[MappingJob] = []
    session_hits = 0
    persistent_hits = 0

    for change_id, context in contexts.items():
        if context is None or context.data is None or context.data.empty:
            continue

        df = context.data
        summaries = context.summaries or {}

        for process_name, group in df.groupby("process_name", sort=False):
            process_key = str(process_name or "")
            summary = summaries.get(process_name) if summaries else None
            functions = (
                summary.functions
                if summary and summary.functions
                else tuple(group.iloc[0].get("process_functions") or ())
            )
            assurances = (
                summary.requirements
                if summary and summary.requirements
                else tuple(group.iloc[0].get("process_requirements") or ())
            )
            extra = (
                summary.raw_text
                if summary
                else str(group.iloc[0].get("process_detail") or "")
            )

            requirement_indices: list[int] = []
            requirement_values: list[str] = []
            for idx in group.index.tolist():
                raw_requirement = str(df.at[idx, "requirement"] or "").strip()
                if not raw_requirement:
                    continue
                requirement_indices.append(int(idx))
                requirement_values.append(raw_requirement)

            if not functions or not requirement_values:
                continue

            request = FunctionMappingRequest(
                functions=functions,
                assurances=assurances,
                requirements=tuple(requirement_values),
                extra=extra,
            )
            signature = build_request_signature(request)

            cached_entry, cache_source = cache_fetcher(signature)
            if cached_entry:
                _apply_cached_result(
                    cached_entry,
                    df,
                    requirement_indices,
                    change_id=str(change_id),
                    process_key=process_key,
                    signature=signature,
                    mapping_results=mapping_results,
                )
                if cache_source == "persistent":
                    persistent_hits += 1
                else:
                    session_hits += 1
                continue

            job_context = MappingContext(
                process_name=process_key,
                change_id=str(change_id),
                functions=functions,
                assurances=assurances,
                requirements=tuple(requirement_values),
                model_name=str(model) if model else "",
            )
            jobs.append(
                MappingJob(
                    change_id=str(change_id),
                    process_key=process_key,
                    dataframe=df,
                    requirement_indices=requirement_indices,
                    request=request,
                    signature=signature,
                    context=job_context,
                )
            )

    return JobBuildResult(
        jobs=jobs,
        mapping_results=mapping_results,
        session_cache_hits=session_hits,
        persistent_cache_hits=persistent_hits,
    )


def _apply_cached_result(
    cached_entry: Mapping[str, Any],
    dataframe: pd.DataFrame,
    requirement_indices: list[int],
    *,
    change_id: str,
    process_key: str,
    signature: str,
    mapping_results: dict[str, dict[str, dict[str, Any]]],
) -> None:
    records, raw_text, errors = apply_cached_mapping(
        cached_entry, dataframe, requirement_indices
    )
    serialized = serialize_records(records)

    mapping_results.setdefault(change_id, {})[process_key] = {
        "signature": signature,
        "records": serialized,
        "raw_text": raw_text,
        "errors": list(errors),
    }


__all__ = ["JobBuildResult", "MappingJob", "build_mapping_jobs"]
