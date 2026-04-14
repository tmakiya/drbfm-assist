"""Refactored PFMEA function mapper with cleaner architecture.

This is a cleaner version of function_mapper.py using the Context Object pattern
to reduce parameter complexity and improve maintainability.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.common.prompt_loader import load_prompt_template
from src.services import llm_gateway
from src.services.llm_executor import LLMExecutor
from src.services.llm_gateway import (
    GenerationConfig as GenerationConfig,  # Explicit re-export for tests
)
from src.services.llm_gateway import build_generation_config
from src.services.llm_retry_policies import RetryPolicies
from src.services.llm_schemas import get_function_mapping_schema

from .mapping_context import MappingContext
from .mapping_logger import CorrectionType, get_mapping_logger

logger = logging.getLogger(__name__)

PROMPT_NAME = "pfmea_function_mapping"
PLACEHOLDER_REASON = "AI応答に割当が返却されませんでした。"
DUPLICATE_ASSIGNMENT_REASON = (
    "AI応答で同じ要求事項に複数の割当が返却されたため再割当が必要です。"
)
INVALID_INDEX_REASON = (
    "AI応答で要求事項インデックスが範囲外だったため再割当が必要です。"
)


@dataclass(frozen=True)
class FunctionMappingRequest:
    """Request for function mapping."""

    functions: Sequence[str]
    assurances: Sequence[str]
    requirements: Sequence[str]
    extra: str | None = None


@dataclass(frozen=True)
class FunctionMappingRecord:
    """Single mapping record between function and requirement."""

    function_index: int
    assurance_index: int
    requirement_index: int
    function: str
    assurance: str
    requirement: str
    reason: str


@dataclass(frozen=True)
class FunctionMappingResponse:
    """Response from function mapping."""

    records: Sequence[FunctionMappingRecord]
    raw_text: str = ""
    missing_requirement_indices: tuple[int, ...] = ()
    recovery_attempts: int = 0
    rate_limit_retries: int = 0
    errors: tuple[str, ...] = ()


class FunctionMappingError(Exception):
    """Error in function mapping process."""

    pass


class MalformedMappingResponseError(FunctionMappingError):
    """AI response could not be parsed as JSON."""

    def __init__(
        self, message: str, *, raw_text: str, original: Exception | None = None
    ) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.original = original


def map_functions_to_requirements(
    model: Any,
    request: FunctionMappingRequest,
    *,
    retry_policy: llm_gateway.RetryPolicy | None = None,
    executor: LLMExecutor | None = None,
    context: MappingContext | None = None,
) -> FunctionMappingResponse:
    """Map functions to requirements using LLM.

    This is the main entry point with a clean interface.
    The context parameter encapsulates all auxiliary information.
    """
    if not request.functions or not request.requirements:
        raise FunctionMappingError(
            "工程の機能または要求事項が空のため、マッピングできません。"
        )

    # Prepare prompt
    prompt_functions = _prepare_prompt_entries(request.functions)
    prompt_assurances = _prepare_prompt_entries(request.assurances)
    prompt_requirements = _prepare_prompt_entries(request.requirements)
    assurance_count = len(request.assurances)
    assurance_index_range = (
        f"1〜{assurance_count}" if assurance_count else "0（製造保証項目なし）"
    )

    template = load_prompt_template(PROMPT_NAME)
    requirement_prompt_count = sum(1 for item in prompt_requirements if item.strip())

    prompt = template.render(
        {
            "function_list": _format_enum_block("工程の機能", prompt_functions),
            "assurance_list": _format_enum_block(
                "製造保証項目", prompt_assurances, allow_empty=True
            ),
            "requirement_list": _format_enum_block("要求事項", prompt_requirements),
            "requirement_count": str(requirement_prompt_count),
            "extra_notes": request.extra.strip() if request.extra else "なし",
            "assurance_index_range": assurance_index_range,
        }
    )

    # Execute LLM
    policy = retry_policy or RetryPolicies.CRITICAL
    generation_config = build_generation_config(temperature=0.0, top_p=0.95)

    logger.debug(
        "PFMEA function mapping prompt prepared (functions=%d, assurances=%d, requirements=%d)",
        len(request.functions),
        len(request.assurances),
        len(request.requirements),
    )

    runner = executor or LLMExecutor(
        model, runner=llm_gateway.run_generation, operation_name="llm_function_mapping"
    )
    response_schema = get_function_mapping_schema(
        function_count=len(request.functions),
        assurance_count=len(request.assurances),
        requirement_count=len(request.requirements),
    )

    result = runner.generate(
        prompt=prompt,
        generation_config=generation_config,
        retry_policy=policy,
        response_mime_type="application/json",
        response_schema=response_schema,
        metadata={
            "request": "pfmea_function_mapping",
            "functions": len(request.functions),
            "assurances": len(request.assurances),
            "requirements": len(request.requirements),
        },
    )

    if result.status != "success":
        message = result.message or "要求事項のマッピングに失敗しました。"
        logger.warning("PFMEA function mapping failed: %s", message)
        raise FunctionMappingError(message)

    content = (result.content or "").strip()
    if not content:
        raise FunctionMappingError("AI応答が空でした。")

    # Parse response with clean context
    records, missing_indices = _parse_mapping_payload(
        content,
        request.functions,
        request.assurances,
        request.requirements,
        context=context,
    )

    return FunctionMappingResponse(
        records=records,
        raw_text=result.content,
        missing_requirement_indices=missing_indices,
    )


def _parse_mapping_payload(
    content: str,
    functions: Sequence[str],
    assurances: Sequence[str],
    requirements: Sequence[str],
    *,
    context: MappingContext | None = None,
) -> tuple[tuple[FunctionMappingRecord, ...], tuple[int, ...]]:
    """Parse LLM response into mapping records.

    Now with a single context parameter instead of many individual ones.
    """
    ctx = context or MappingContext(
        functions=tuple(functions),
        assurances=tuple(assurances),
        requirements=tuple(requirements),
    )

    prepared = _prepare_json_content(content)

    try:
        payload = json.loads(prepared)
    except json.JSONDecodeError as exc:
        preview = prepared[:160].replace("\n", "\\n")
        logger.error(
            "PFMEA function mapping 応答のJSON解析に失敗: %s | content_preview=%s",
            exc,
            preview,
            exc_info=True,
        )
        raise MalformedMappingResponseError(
            f"AI応答をJSONとして解析できませんでした（先頭: {preview}）。",
            raw_text=prepared,
            original=exc,
        ) from exc

    if isinstance(payload, dict) and "records" in payload:
        records_payload = payload["records"]
    else:
        records_payload = payload

    if not isinstance(records_payload, list):
        raise FunctionMappingError("AI応答の形式が不正です。")

    # Process each record
    normalized_functions = [str(item).strip() for item in functions]
    normalized_assurances = [str(item).strip() for item in assurances]
    normalized_requirements = [str(item).strip() for item in requirements]

    if not normalized_assurances:
        normalized_assurances = ["" for _ in normalized_functions]

    total_requirements = len(normalized_requirements)
    records_by_requirement: dict[int, FunctionMappingRecord] = {}
    placeholder_reasons: dict[int, str] = {}

    for entry in records_payload:
        if not isinstance(entry, dict):
            raise FunctionMappingError("AI応答に辞書以外の要素が含まれています。")

        # Extract entry data
        entry_function = str(entry.get("function") or "").strip()
        entry_assurance = str(entry.get("assurance") or "").strip()
        entry_requirement = str(entry.get("requirement") or "").strip()
        raw_requirement_index = entry.get("requirement_index")
        raw_requirement_numeric = _coerce_int(raw_requirement_index)

        # Get current requirement text
        current_requirement_text = entry_requirement
        if raw_requirement_numeric and 1 <= raw_requirement_numeric <= len(
            normalized_requirements
        ):
            current_requirement_text = normalized_requirements[
                raw_requirement_numeric - 1
            ]

        # Update context for this entry
        entry_ctx = ctx.with_requirement(
            index=raw_requirement_numeric or 0,
            text=current_requirement_text,
            ai_entry=entry,
        )

        # Resolve indices with cleaner interface
        function_index = _resolve_index(
            entry.get("function_index"),
            len(normalized_functions),
            "function_index",
            fallback_text=entry_function,
            candidates=normalized_functions,
            context=entry_ctx,
        )

        assurance_index = _resolve_index(
            entry.get("assurance_index"),
            len(normalized_assurances),
            "assurance_index",
            allow_empty=not assurances,
            fallback_text=entry_assurance,
            candidates=normalized_assurances,
            context=entry_ctx,
            clamp_on_error=True,  # Always clamp: Gemini may ignore schema bounds
        )

        requirement_index = _resolve_index(
            entry.get("requirement_index"),
            len(normalized_requirements),
            "requirement_index",
            fallback_text=entry_requirement,
            candidates=normalized_requirements,
            context=entry_ctx,
        )

        reason = str(entry.get("reason") or "").strip()
        if not reason:
            raise FunctionMappingError("AI応答のreasonが空です。")

        # Build record
        function_text = entry_function or normalized_functions[function_index - 1]
        assurance_text = (
            entry_assurance
            or normalized_assurances[
                (assurance_index - 1) if assurance_index else (function_index - 1)
            ]
        )
        requirement_text = (
            entry_requirement or normalized_requirements[requirement_index - 1]
        )

        invalid_requirement_index = raw_requirement_numeric is not None and not (
            1 <= raw_requirement_numeric <= total_requirements
        )
        matched_requirement_by_text = bool(entry_requirement) and (
            _normalize_lookup_text(entry_requirement)
            == _normalize_lookup_text(normalized_requirements[requirement_index - 1])
        )

        if invalid_requirement_index and not matched_requirement_by_text:
            placeholder_reasons.setdefault(requirement_index, INVALID_INDEX_REASON)
            logger.warning(
                (
                    "PFMEA function mapping 応答の要求事項インデックスが範囲外のため"
                    "プレースホルダーへ置換します (index=%s, resolved=%d)"
                ),
                raw_requirement_numeric,
                requirement_index,
            )
            records_by_requirement.pop(requirement_index, None)
            continue

        # Store record
        existing = records_by_requirement.get(requirement_index)
        if existing is not None:
            placeholder_reasons.setdefault(
                requirement_index, DUPLICATE_ASSIGNMENT_REASON
            )
            logger.warning(
                "PFMEA function mapping 応答に同一要求事項の重複割当が含まれています (index=%d)",
                requirement_index,
            )
            records_by_requirement.pop(requirement_index, None)
            continue

        records_by_requirement[requirement_index] = FunctionMappingRecord(
            function_index=function_index,
            assurance_index=assurance_index or function_index,
            requirement_index=requirement_index,
            function=function_text,
            assurance=assurance_text,
            requirement=requirement_text,
            reason=reason,
        )

    # Handle missing requirements
    missing_requirement_indices = set(range(1, total_requirements + 1)) - set(
        records_by_requirement.keys()
    )

    # Build final records list
    records = []
    for requirement_index in range(1, total_requirements + 1):
        existing = records_by_requirement.get(requirement_index)
        if existing is not None:
            records.append(existing)
        else:
            requirement_text = normalized_requirements[requirement_index - 1]
            reason_text = placeholder_reasons.get(requirement_index, PLACEHOLDER_REASON)
            records.append(
                FunctionMappingRecord(
                    function_index=0,
                    assurance_index=0,
                    requirement_index=requirement_index,
                    function="",
                    assurance="",
                    requirement=requirement_text,
                    reason=reason_text,
                )
            )

    return tuple(records), tuple(sorted(missing_requirement_indices))


def _resolve_index(
    raw_value: Any,
    upper_bound: int,
    label: str,
    *,
    allow_empty: bool = False,
    fallback_text: str = "",
    candidates: Iterable[str] = (),
    context: MappingContext | None = None,
    clamp_on_error: bool = True,
) -> int:
    """Resolve index value with automatic correction and logging.

    Clean interface with a single context parameter.
    """
    ctx = context or MappingContext()

    # Try to parse as number
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        if allow_empty:
            return 0
        raw_value = fallback_text

    numeric_index = _coerce_int(raw_value)

    # Check if in valid range
    if numeric_index is not None and 1 <= numeric_index <= upper_bound:
        return numeric_index

    if allow_empty and numeric_index in (None, 0):
        return 0

    # Try text matching
    if fallback_text:
        candidates_list = list(candidates)
        normalized_fallback = _normalize_lookup_text(fallback_text)
        normalized_candidates = [_normalize_lookup_text(c) for c in candidates_list]

        matches = [
            i + 1
            for i, c in enumerate(normalized_candidates)
            if c == normalized_fallback
        ]

        if len(matches) == 1 and 1 <= matches[0] <= upper_bound:
            return matches[0]

    # Apply correction and log
    if numeric_index is not None and upper_bound > 0:
        if clamp_on_error:
            if numeric_index < 1:
                corrected = 1
                correction_type = CorrectionType.BELOW_LOWER_BOUND
            else:
                corrected = upper_bound
                correction_type = CorrectionType.OVER_UPPER_BOUND

            # Log the correction with full context
            get_mapping_logger().log_index_correction(
                process_name=ctx.process_name,
                change_id=ctx.change_id,
                field_name=label,
                original_value=numeric_index,
                corrected_value=corrected,
                upper_bound=upper_bound,
                correction_type=correction_type,
                requirement_index=ctx.current_requirement_index,
                requirement_text=ctx.current_requirement_text,
                function_list=list(candidates) if candidates else [],
                assurance_list=list(ctx.assurances),
                ai_response_entry=ctx.current_ai_entry,
                retry_attempt=ctx.retry_attempt,
                recovery_method=ctx.recovery_method,
                chunk_info=ctx.chunk_info,
            )

            return corrected

        min_bound = 1
        max_bound = upper_bound
        logger.warning(
            "PFMEA function mapping index out of range; no clamp applied",
            extra={
                "field_name": label,
                "original_value": numeric_index,
                "min_bound": min_bound,
                "max_bound": max_bound,
                "allow_empty": allow_empty,
                "clamp_on_error": clamp_on_error,
                "process_name": ctx.process_name,
                "change_id": ctx.change_id,
                "requirement_index": ctx.current_requirement_index,
                "requirement_text": ctx.current_requirement_text,
                "function_count": len(ctx.functions),
                "assurance_count": len(ctx.assurances),
                "requirement_count": len(ctx.requirements),
                "ai_response_entry": ctx.current_ai_entry,
                "recovery_method": ctx.recovery_method,
                "retry_attempt": ctx.retry_attempt,
                "chunk_info": ctx.chunk_info,
            },
        )
        get_mapping_logger().log_index_error(
            process_name=ctx.process_name,
            change_id=ctx.change_id,
            field_name=label,
            original_value=numeric_index,
            upper_bound=upper_bound,
            requirement_index=ctx.current_requirement_index,
            requirement_text=ctx.current_requirement_text,
            function_list=list(ctx.functions),
            assurance_list=list(ctx.assurances),
            ai_response_entry=ctx.current_ai_entry,
            retry_attempt=ctx.retry_attempt,
            recovery_method=ctx.recovery_method,
            chunk_info=ctx.chunk_info,
        )
        raise FunctionMappingError(
            f"{label} が範囲外です: {numeric_index!r} (許容: {min_bound}〜{max_bound})"
        )

    # Error cases
    if allow_empty:
        raise FunctionMappingError(f"{label} が欠落しています。")
    raise FunctionMappingError(f"{label} が範囲外です: {raw_value!r}")


# Utility functions (unchanged)
def _prepare_prompt_entries(values: Sequence[str]) -> tuple[str, ...]:
    """Prepare prompt entries with duplication markers."""
    prepared: list[str] = []
    occurrences: dict[str, int] = {}
    for value in values:
        text = str(value or "").strip()
        if text:
            normalized = re.sub(r"\s+", " ", text)
            count = occurrences.get(normalized, 0) + 1
            occurrences[normalized] = count
            annotated = f"{normalized} (再掲{count})" if count > 1 else normalized
            prepared.append(annotated)
        else:
            prepared.append("")
    return tuple(prepared)


def _format_enum_block(
    title: str, values: Sequence[str], *, allow_empty: bool = False
) -> str:
    """Format enumerated block for prompt."""
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        if allow_empty:
            return f"{title} (全0件): なし"
        raise FunctionMappingError(f"{title} が空のためマッピングできません。")
    lines = [f"{title} (全{len(items)}件):"]
    for idx, value in enumerate(items, start=1):
        lines.append(f"{idx}. {value}")
    return "\n".join(lines)


def _prepare_json_content(raw: str) -> str:
    """Prepare JSON content from raw response."""
    text = raw.strip()
    if not text:
        return text

    # Remove code fences
    for fence in ("```", "~~~"):
        if text.startswith(fence):
            parts = text.split(fence)
            for part in parts[1:]:
                candidate = part.strip()
                if not candidate:
                    continue
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].lstrip(" :\n\r\t")
                text = candidate
                break
            else:
                text = parts[0].strip()
            break

    # Find JSON start
    text = text.strip()
    if text and text[0] not in ("{", "["):
        for idx, char in enumerate(text):
            if char in ("{", "["):
                text = text[idx:]
                break
    return _extract_json_fragment(text)


def _extract_json_fragment(text: str) -> str:
    """Extract valid JSON fragment from text."""
    if not text:
        return text

    start_idx: int | None = None
    stack: list[str] = []
    matching = {"{": "}", "[": "]"}

    for idx, char in enumerate(text):
        if char in matching:
            if start_idx is None:
                start_idx = idx
            stack.append(char)
        elif char in matching.values() and stack:
            opener = stack.pop()
            expected = matching[opener]
            if char != expected:
                return (
                    text[start_idx : idx + 1]
                    if start_idx is not None
                    else text[: idx + 1]
                )
            if not stack and start_idx is not None:
                return text[start_idx : idx + 1]

    if start_idx is not None and stack:
        return text[start_idx:]
    return text


def _coerce_int(value: Any) -> int | None:
    """Try to convert value to integer."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_lookup_text(value: str) -> str:
    """Normalize text for matching."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def is_placeholder_record(record: FunctionMappingRecord) -> bool:
    """Check if record is a placeholder."""
    return (
        not record.function.strip()
        and not record.assurance.strip()
        and record.reason.strip().startswith(PLACEHOLDER_REASON)
    )


def build_request_signature(request: FunctionMappingRequest) -> str:
    """Build cache signature for request."""
    payload = {
        "functions": [str(item).strip() for item in request.functions],
        "assurances": [str(item).strip() for item in request.assurances],
        "requirements": [str(item).strip() for item in request.requirements],
        "extra": (request.extra or "").strip(),
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def serialize_records(records: Sequence[FunctionMappingRecord]) -> list[dict[str, Any]]:
    """Serialize records to dictionary format."""
    return [
        {
            "function_index": record.function_index,
            "assurance_index": record.assurance_index,
            "requirement_index": record.requirement_index,
            "function": record.function,
            "assurance": record.assurance,
            "requirement": record.requirement,
            "reason": record.reason,
        }
        for record in records
    ]


def deserialize_records(
    payload: Sequence[Mapping[str, Any]],
) -> tuple[FunctionMappingRecord, ...]:
    """Deserialize records from dictionary format."""
    records: list[FunctionMappingRecord] = []
    for entry in payload:
        records.append(
            FunctionMappingRecord(
                function_index=int(entry.get("function_index", 0)),
                assurance_index=int(entry.get("assurance_index", 0)),
                requirement_index=int(entry.get("requirement_index", 0)),
                function=str(entry.get("function", "")),
                assurance=str(entry.get("assurance", "")),
                requirement=str(entry.get("requirement", "")),
                reason=str(entry.get("reason", "")),
            )
        )
    return tuple(records)
