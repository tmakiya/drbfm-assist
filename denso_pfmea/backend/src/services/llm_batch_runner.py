from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.common.bop import ChangeRecord
from src.common.perf import record_event
from src.common.prompt_loader import aload_prompt_template
from src.services import llm_gateway
from src.services.circuit_breaker import get_global_breaker
from src.services.llm_executor import LLMExecutor
from src.services.llm_gateway import build_generation_config
from src.services.llm_metrics import metrics_enabled
from src.services.llm_schemas import get_pfmea_assessment_schema_for_model
from src.services.llm_self_consistency import aggregate_by_majority_vote
from src.services.pfmea.baseline_examples import (
    collect_baseline_examples,
    format_baseline_examples_json,
)
from src.services.pfmea_context import PfmeaContext

PROMPT_TEMPLATE_NAME = "pfmea_assessment"

BLOCK_DEFINITION = (
    "ブロック: 特定の組付けや加工をまとめた工程単位で、複数のステーションで構成される。"
)
STATION_DEFINITION = (
    "ステーション: 1台のマシン（作業セル）を指し、ブロックを構成する最小単位。"
)

_SELF_CONSISTENCY_SAMPLES_ENV = "SOL_PFMEA_SELF_CONSISTENCY_SAMPLES"
_SELF_CONSISTENCY_FIELDS_ENV = "SOL_PFMEA_SELF_CONSISTENCY_FIELDS"
_DEFAULT_SELF_CONSISTENCY_FIELDS = ("判断", "自信度")


def _escape(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return text.replace("|", "\\|")


def _chunk_requirements(
    functions: tuple[str, ...], requirements: tuple[str, ...]
) -> tuple[tuple[str, ...], ...]:
    if not functions:
        return (requirements,) if requirements else ()
    groups: list[tuple[str, ...]] = []
    req_index = 0
    total_reqs = len(requirements)
    total_funcs = len(functions)
    for idx in range(total_funcs):
        remaining_funcs = total_funcs - idx
        remaining_reqs = total_reqs - req_index
        if remaining_funcs <= 0:
            break
        if remaining_reqs <= 0:
            groups.append(())
            continue
        take = max(1, math.ceil(remaining_reqs / remaining_funcs))
        segment = tuple(requirements[req_index : req_index + take])
        if not segment and remaining_reqs > 0:
            segment = (requirements[req_index],)
            take = 1
        groups.append(segment)
        req_index += take
    if req_index < total_reqs and groups:
        tail = list(groups[-1]) + list(requirements[req_index:])
        groups[-1] = tuple(tail)
    while len(groups) < len(functions):
        groups.append(())
    return tuple(groups)


def _format_metadata(metadata: Mapping[str, dict[str, str]]) -> str:
    if not metadata:
        return "情報なし"
    blocks: list[str] = []
    for scope, values in metadata.items():
        if not values:
            continue
        entries = "<br>".join(
            f"{_escape(key)}: {_escape(value)}" for key, value in values.items()
        )
        if not entries:
            continue
        blocks.append(f"{_escape(scope)}:<br>{entries}")
    return "<br><br>".join(blocks) if blocks else "情報なし"


def _format_value(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text else "（なし）"


def _format_neighbor_summary(change: ChangeRecord) -> str:
    entries: list[str] = []
    if change.preceding_part_label:
        entries.append(
            f"前工程（{_escape(change.preceding_part_label)}）: 流用元={_escape(_format_value(change.preceding_original_value))}"
            f" / 変更後={_escape(_format_value(change.preceding_new_value))}"
        )
    if change.following_part_label:
        entries.append(
            f"後工程（{_escape(change.following_part_label)}）: 流用元={_escape(_format_value(change.following_original_value))}"
            f" / 変更後={_escape(_format_value(change.following_new_value))}"
        )
    if not entries:
        return "前後工程の部品情報: 情報なし"
    return "前後工程の部品情報:<br>" + "<br>".join(entries)


def get_compound_changes_info(
    change: ChangeRecord,
    all_changes: list[ChangeRecord],
) -> str:
    """Get information about other changes in the same process.

    Args:
        change: The current change record.
        all_changes: All change records in the batch.

    Returns:
        A formatted string describing compound changes, or a message indicating
        this is a single change.
    """
    key = (change.variant_id, change.block, change.station)
    same_process = [
        c
        for c in all_changes
        if (c.variant_id, c.block, c.station) == key and c.change_id != change.change_id
    ]

    if not same_process:
        return "この変化点は単独です。"

    lines = [
        f"同一工程（{_escape(change.block)} > {_escape(change.station)}）で以下の部品も同時に変更されています:"
    ]
    for c in same_process[:5]:  # Max 5 items
        lines.append(
            f"- {_escape(c.part_label)}: {_escape(c.change_type)}"
            f"（{_escape(c.original_value or '新規')} → {_escape(c.new_value or '削除')}）"
        )

    if len(same_process) > 5:
        lines.append(f"- 他 {len(same_process) - 5} 件")

    lines.append("")
    lines.append("これらの変化点の**相互作用**によるリスクも検討してください。")

    return "<br>".join(lines)


def _int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    if minimum is not None:
        return max(minimum, value)
    return value


def _resolve_self_consistency_fields() -> tuple[str, ...]:
    raw = os.getenv(_SELF_CONSISTENCY_FIELDS_ENV, "").strip()
    if not raw:
        return _DEFAULT_SELF_CONSISTENCY_FIELDS
    fields = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(fields) if fields else _DEFAULT_SELF_CONSISTENCY_FIELDS


def _extract_model_name(model: Any) -> str | None:
    """Extract model name from a LangChain model or legacy dict."""
    # LangChain BaseChatModel
    if hasattr(model, "model"):
        return str(model.model)
    if hasattr(model, "model_name"):
        return str(model.model_name)
    # Legacy dict format
    if isinstance(model, Mapping):
        value = model.get("model_name")
        if value:
            return str(value)
    return None


def _extract_results_from_json(content: str) -> list[dict[str, Any]] | None:
    if not content:
        return None
    text = content.strip()
    json_match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if json_match:
        text = json_match.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        results = payload.get("results")
        return results if isinstance(results, list) else None
    if isinstance(payload, list):
        return payload
    return None


def _aggregate_self_consistency_rows(
    samples: list[list[dict[str, Any]]],
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not samples:
        return []
    base = [dict(row) for row in samples[0]]
    min_len = min(len(sample) for sample in samples)
    if min_len < len(base):
        base = base[:min_len]
    for idx in range(min_len):
        row_samples = [sample[idx] for sample in samples if idx < len(sample)]
        aggregated, _ = aggregate_by_majority_vote(row_samples, fields)
        for field in fields:
            if field in aggregated:
                base[idx][field] = aggregated[field]
    return base


def _build_assessment_generation_config() -> Any:
    kwargs: dict[str, Any] = {"temperature": 0.2, "top_p": 0.9}
    return build_generation_config(**kwargs)


def build_pfmea_context_markdown(context: PfmeaContext | None) -> str:
    if context is None or context.data is None or context.data.empty:
        return "該当する既存PFMEAは見つかりませんでした。"

    df = context.data
    summaries = context.summaries or {}

    sections = []
    if context.block:
        sections.append(f"## PFMEAブロック: {context.block}")

    for process_name, group in df.groupby("process_name"):
        if group.empty:
            continue
        header_lines = []
        name = process_name or "（工程名未設定）"
        header_lines.append(f"### 工程: {name}")

        detail = str(group.iloc[0].get("process_detail") or "").strip()
        if detail:
            escaped_detail = detail.replace("|", "\\|")
            header_lines.append(f"> {escaped_detail}")

        summary = summaries.get(process_name) if summaries else None
        if summary:
            notes: list[str] = []
            raw_text = summary.raw_text.strip()
            if raw_text:
                notes.append(_escape(raw_text).replace("\n", "<br>"))
            for label, items in summary.extra_sections.items():
                if not items:
                    continue
                item_text = "<br>".join(_escape(item) for item in items if item)
                if item_text:
                    notes.append(f"{_escape(label)}: {item_text}")
            if notes:
                header_lines.append("**工程備考**")
                header_lines.append("- " + "<br>- ".join(notes))

        functions = tuple(group.iloc[0].get("process_functions") or ())
        requirements = tuple(group.iloc[0].get("process_requirements") or ())
        if functions:
            req_groups = _chunk_requirements(functions, requirements)
            table = ["|機能No|工程の機能|対応する製造保証項目|", "|---|---|---|"]
            for idx, func in enumerate(functions, start=1):
                paired_reqs = req_groups[idx - 1] if idx - 1 < len(req_groups) else ()
                req_text = (
                    "<br>".join(_escape(item) for item in paired_reqs if item) or "―"
                )
                table.append(f"|{idx}|{_escape(func)}|{req_text}|")
            header_lines.append("\n".join(table))
        elif requirements:
            req_text = (
                "<br>".join(_escape(item) for item in requirements if item) or "―"
            )
            header_lines.append(f"- 製造保証項目: {req_text}")

        risk_rows = group.sort_values(by=["rpn", "severity"], ascending=[False, False])
        risk_table = [
            "|No.|要求事項|故障モード|故障影響|原因|対策|検出方法|推奨処置|工程票反映|責任部署/担当|S|O|D|RPN|重点管理|",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for idx, (_, row) in enumerate(risk_rows.iterrows(), start=1):
            requirement = _escape(row.get("requirement") or "―") or "―"
            failure_mode = _escape(row.get("failure_mode") or "―") or "―"
            effect = _escape(row.get("effect") or "―") or "―"
            cause = _escape(row.get("cause") or "―") or "―"
            prevention = _escape(row.get("prevention") or "―") or "―"
            detection_control = _escape(row.get("detection_control") or "―") or "―"
            recommended_action = _escape(row.get("recommended_action") or "―") or "―"
            process_sheet = _escape(row.get("process_sheet_reflection") or "―") or "―"
            responsible_owner = _escape(row.get("responsible_owner") or "―") or "―"
            severity = str(row.get("severity") or "")
            occurrence = str(row.get("occurrence") or "")
            detection = str(row.get("detection") or "")
            rpn = str(row.get("rpn") or "")
            priority = _escape(row.get("priority_designation") or "") or "―"
            risk_table.append(
                f"|{idx}|{requirement}|{failure_mode}|{effect}|{cause}|{prevention}|"
                f"{detection_control}|{recommended_action}|{process_sheet}|{responsible_owner}|"
                f"{severity}|{occurrence}|{detection}|{rpn}|{priority}|"
            )
        header_lines.append("\n".join(risk_table))
        sections.append("\n\n".join(header_lines))

    return "\n\n".join(sections)


# =============================================================================
# Async versions for LangGraph integration
# =============================================================================


async def agenerate_llm_assessment(
    model: BaseChatModel,
    change: ChangeRecord,
    context: PfmeaContext | None,
    *,
    template_name: str = PROMPT_TEMPLATE_NAME,
    executor: LLMExecutor | None = None,
    response_schema: dict[str, Any] | None = None,
    use_structured_output: bool = True,
    compound_changes_info: str = "この変化点は単独です。",
) -> llm_gateway.LLMCallResult:
    """非同期版 LLM assessment 生成。"""
    context_text = build_pfmea_context_markdown(context)
    baseline_examples = format_baseline_examples_json(
        collect_baseline_examples(
            (context,) if context is not None else (),
            limit=5,
        )
    )
    template = await aload_prompt_template(template_name)
    keywords_value = ", ".join(change.keywords) if change.keywords else "未分類"
    variant_metadata_text = _format_metadata(change.variant_metadata)
    neighbor_summary = _format_neighbor_summary(change)
    data_quality_note = (
        "品番は同じですが部品名称が異なります。元データの整合性を確認してください。"
        if change.is_label_mismatch
        else "特記事項なし"
    )
    prompt = template.render(
        {
            "variant_id": change.variant_id,
            "block": change.block,
            "station": change.station,
            "block_definition": BLOCK_DEFINITION,
            "station_definition": STATION_DEFINITION,
            "variant_metadata": variant_metadata_text,
            "neighbor_summary": neighbor_summary,
            "data_quality_warning": data_quality_note,
            "part_label": change.part_label,
            "source_part_label": change.original_part_label or "（なし）",
            "target_part_label": change.updated_part_label or "（なし）",
            "change_type": change.change_type,
            "original_value": change.original_value or "（なし）",
            "new_value": change.new_value or "（なし）",
            "keywords": keywords_value,
            "shape_feature": change.shape_feature or "記載なし",
            "context_text": context_text,
            "baseline_examples": baseline_examples,
            "compound_changes_info": compound_changes_info,
        }
    )

    model_name = _extract_model_name(model)
    if response_schema is None and use_structured_output:
        response_schema = get_pfmea_assessment_schema_for_model(model_name)

    runner = executor or LLMExecutor(model, operation_name="llm_assessment")

    # Structured Output を使用するかどうかを決定
    effective_schema = response_schema if use_structured_output else None
    mime_type = "application/json" if effective_schema else None

    # Self-Consistency サポート
    sample_count = _int_env(_SELF_CONSISTENCY_SAMPLES_ENV, 1, minimum=1)
    if sample_count > 1 and effective_schema is not None:
        return await _agenerate_self_consistent_assessment(
            runner=runner,
            prompt=prompt,
            generation_config=_build_assessment_generation_config(),
            response_schema=effective_schema,
            response_mime_type=mime_type,
            metadata={
                "change_id": change.change_id,
                "variant_id": change.variant_id,
                "block": change.block or "",
                "station": change.station or "",
            },
            sample_count=sample_count,
        )

    return await runner.agenerate(
        prompt=prompt,
        generation_config=_build_assessment_generation_config(),
        response_mime_type=mime_type,
        response_schema=effective_schema,
        metadata={
            "change_id": change.change_id,
            "variant_id": change.variant_id,
            "block": change.block or "",
            "station": change.station or "",
        },
    )


async def _agenerate_self_consistent_assessment(
    *,
    runner: LLMExecutor,
    prompt: str,
    generation_config: Any,
    response_schema: dict[str, Any],
    response_mime_type: str | None,
    metadata: Mapping[str, Any],
    sample_count: int,
) -> llm_gateway.LLMCallResult:
    """非同期版 Self-Consistency assessment 生成。

    複数回のLLM呼び出しを行い、多数決で結果を集約する。
    """
    fields = _resolve_self_consistency_fields()
    samples: list[list[dict[str, Any]]] = []
    last_error = "AI推定結果を取得できませんでした。"

    # 並列でサンプルを取得
    async def _get_sample(index: int) -> tuple[int, llm_gateway.LLMCallResult]:
        sample_meta = dict(metadata)
        sample_meta["self_consistency_sample"] = index + 1
        sample_meta["self_consistency_total"] = sample_count
        result = await runner.agenerate(
            prompt=prompt,
            generation_config=generation_config,
            response_mime_type=response_mime_type,
            response_schema=response_schema,
            metadata=sample_meta,
        )
        return index, result

    tasks = [_get_sample(i) for i in range(sample_count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            last_error = str(res)
            continue
        _, result = res
        if result.status != "success":
            last_error = result.message or last_error
            continue
        rows = _extract_results_from_json(result.content)
        if rows is None:
            last_error = "AI応答をJSONとして解析できませんでした。"
            continue
        samples.append(rows)

    if not samples:
        return llm_gateway.LLMCallResult(
            status="error",
            content="",
            message=last_error,
        )

    aggregated_rows = _aggregate_self_consistency_rows(samples, fields)
    if not aggregated_rows:
        return llm_gateway.LLMCallResult(
            status="error",
            content="",
            message="Self-consistency集約に失敗しました。",
        )

    content = json.dumps({"results": aggregated_rows}, ensure_ascii=False)
    return llm_gateway.LLMCallResult(
        status="success",
        content=content,
        message="",
    )


async def _aevaluate_change_with_llm(
    model: BaseChatModel,
    change: ChangeRecord,
    context: PfmeaContext | None,
    *,
    executor: LLMExecutor | None = None,
    compound_changes_info: str = "この変化点は単独です。",
) -> tuple[str, dict[str, str]]:
    """非同期版 LLM 評価。"""
    import logging

    logger = logging.getLogger(__name__)
    try:
        result = await agenerate_llm_assessment(
            model,
            change,
            context,
            executor=executor,
            compound_changes_info=compound_changes_info,
        )
    except Exception as exc:
        logger.exception(
            "AI推定処理でエラーが発生しました (change_id=%s): %s",
            change.change_id,
            exc,
        )
        message = str(exc).strip() or repr(exc)
        return change.change_id, {
            "status": "error",
            "content": "",
            "message": f"AI推定処理でエラーが発生しました: {message}",
        }
    return change.change_id, {
        "status": result.status,
        "content": result.content,
        "message": result.message,
    }


async def run_llm_batch_async(
    model: BaseChatModel,
    changes: Iterable[ChangeRecord],
    pfmea_context: Mapping[str, PfmeaContext | None],
    *,
    max_concurrency: int = 4,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, dict[str, str]]:
    """非同期版バッチ処理。asyncio.gather を使用して並列実行する。

    Args:
        model: LangChain BaseChatModel インスタンス
        changes: 評価対象の変更レコード
        pfmea_context: 変更IDごとのPFMEAコンテキスト
        max_concurrency: 最大並列数 (Semaphore で制御)
        progress_callback: 進捗コールバック

    Returns:
        変更IDごとの評価結果
    """
    changes_list = list(changes)
    if not changes_list:
        return {}

    start_time = time.perf_counter()
    breaker = get_global_breaker()
    executor = LLMExecutor(model, operation_name="llm_assessment")
    semaphore = asyncio.Semaphore(max_concurrency)
    completed = 0
    total = len(changes_list)

    async def _task(change: ChangeRecord) -> tuple[str, dict[str, str]]:
        nonlocal completed
        async with semaphore:
            context_bundle = pfmea_context.get(change.change_id)
            compound_info = get_compound_changes_info(change, changes_list)
            result = await _aevaluate_change_with_llm(
                model,
                change,
                context_bundle,
                executor=executor,
                compound_changes_info=compound_info,
            )

            # Record per-task success/failure to Circuit Breaker
            change_id, assessment_result = result
            if assessment_result.get("status") == "success":
                breaker.record_success()
            else:
                is_rate_limit = LLMExecutor.is_rate_limit_message(
                    assessment_result.get("message", "")
                )
                breaker.record_failure(
                    is_rate_limit=is_rate_limit,
                    message=assessment_result.get("message", ""),
                )

            if progress_callback is not None:
                completed += 1
                progress_callback(completed, total)

            return result

    tasks = [_task(change) for change in changes_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 例外をエラー結果に変換
    result_dict: dict[str, dict[str, str]] = {}
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            change_id = changes_list[i].change_id
            result_dict[change_id] = {
                "status": "error",
                "content": "",
                "message": f"AI推定処理でエラーが発生しました: {res}",
            }
        else:
            change_id, assessment = res
            result_dict[change_id] = assessment

    if metrics_enabled():
        record_event(
            "llm.run_batch_async",
            start=start_time,
            end=time.perf_counter(),
            metadata={"phase": "llm", "changes": len(changes_list)},
        )

    return result_dict
