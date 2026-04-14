from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.common.pfmea import DEFAULT_RATING_SCALES, build_rating_markdown
from src.common.prompt_loader import aload_prompt_template
from src.services import llm_gateway
from src.services.circuit_breaker import get_global_breaker
from src.services.llm_executor import LLMExecutor
from src.services.llm_gateway import build_generation_config
from src.services.llm_retry_policies import RetryPolicies
from src.services.llm_schemas import RISK_RATING_SCHEMA
from src.services.pfmea.baseline_examples import format_baseline_examples_json

logger = logging.getLogger(__name__)

PROMPT_NAME = "pfmea_risk_rating"


@dataclass(frozen=True)
class RiskRatingRow:
    """評価対象となる PFMEA 行のサマリ。"""

    rating_id: str
    requirement: str
    failure_mode: str
    effect: str
    cause: str
    judgement: str
    reason: str
    prevention: str = ""
    detection_method: str = ""
    recommended_action: str = ""
    additional_notes: str = ""


@dataclass(frozen=True)
class RiskRatingGroup:
    """工程の機能単位で束ねた評価リクエスト。"""

    group_id: str
    process_name: str
    process_function: str
    assurances: tuple[str, ...]
    rows: tuple[RiskRatingRow, ...]
    change_summaries: tuple[str, ...] = ()
    baseline_examples: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class RiskRatingRecord:
    """単一行の評価結果。"""

    rating_id: str
    impact: int
    occurrence: int
    detection: int
    rationale: str
    impact_reason: str = ""
    occurrence_reason: str = ""
    detection_reason: str = ""

    def formatted_indicator_rationale(self) -> str:
        """Format per-indicator rationale sentences joined by newline."""

        def _normalize_sentence(text: str, label: str) -> str:
            stripped = text.strip()
            if not stripped:
                stripped = (
                    self.rationale.strip() or f"{label}の根拠情報が提供されていません。"
                )
            if stripped.endswith(("。", "！", "!", "？", "?", ".")):
                return stripped
            return f"{stripped}。"

        sentences: list[str] = []
        for label, score, reason in (
            ("影響度合", self.impact, self.impact_reason),
            ("発生度合", self.occurrence, self.occurrence_reason),
            ("検出度合", self.detection, self.detection_reason),
        ):
            detail = _normalize_sentence(reason, label)
            sentences.append(f"{label}({score}): {detail}")
        return "\n".join(sentences)


@dataclass(frozen=True)
class RiskRatingResponse:
    group_id: str
    records: tuple[RiskRatingRecord, ...]
    raw_text: str = ""


class RiskRatingError(RuntimeError):
    """リスク評価ステージの基底例外。"""


class MalformedRiskRatingResponseError(RiskRatingError):
    """AI応答が JSON として解釈できない場合の例外。"""

    def __init__(self, message: str, *, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


def _format_assurance_text(values: Sequence[str]) -> str:
    cleaned = [value for value in (item.strip() for item in values) if value]
    if not cleaned:
        return "該当なし"
    return " / ".join(cleaned)


def _format_rows_section(group: RiskRatingGroup) -> str:
    lines: list[str] = []
    for index, row in enumerate(group.rows, start=1):
        lines.append(f"- 対象{index}")
        lines.append(f"  行ID: {row.rating_id or '(ID未設定)'}")
        lines.append(f"  要求事項: {row.requirement or '（未記載）'}")
        lines.append(f"  故障モード: {row.failure_mode or '（未記載）'}")
        lines.append(f"  故障の影響: {row.effect or '（未記載）'}")
        lines.append(f"  故障原因: {row.cause or '（未記載）'}")
        if row.judgement:
            lines.append(f"  現行判断: {row.judgement}")
        if row.reason:
            lines.append(f"  追加理由: {row.reason}")
        if row.prevention:
            lines.append(f"  現行予防策: {row.prevention}")
        if row.detection_method:
            lines.append(f"  現行検出方法: {row.detection_method}")
        if row.recommended_action:
            lines.append(f"  推奨処置: {row.recommended_action}")
        if row.additional_notes:
            lines.append(f"  補足: {row.additional_notes}")
    if not lines:
        lines.append("- 対象1")
        lines.append("  行ID: （行が提供されていません）")
    return "\n".join(lines)


async def _abuild_prompt(group: RiskRatingGroup) -> str:
    template = await aload_prompt_template(PROMPT_NAME)
    severity_table = build_rating_markdown(
        DEFAULT_RATING_SCALES.severity, "影響度合の評価基準"
    )
    occurrence_table = build_rating_markdown(
        DEFAULT_RATING_SCALES.occurrence, "発生度合の評価基準"
    )
    detection_table = build_rating_markdown(
        DEFAULT_RATING_SCALES.detection, "検出度合の評価基準"
    )
    assurance_text = _format_assurance_text(group.assurances)
    change_overview = (
        "\n".join(group.change_summaries)
        if group.change_summaries
        else "変化点情報が提供されていません。"
    )
    baseline_section = format_baseline_examples_json(group.baseline_examples)
    rows_section = _format_rows_section(group)
    context = {
        "process_name": group.process_name or "（工程名未設定）",
        "process_function": group.process_function or "（工程の機能未設定）",
        "assurance_text": assurance_text,
        "severity_table": severity_table,
        "occurrence_table": occurrence_table,
        "detection_table": detection_table,
        "rows_section": rows_section,
        "change_overview": change_overview,
        "baseline_examples": baseline_section,
    }
    return template.render(context)


def _parse_risk_rating_payload(
    payload: str,
) -> tuple[str, str, tuple[RiskRatingRecord, ...]]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MalformedRiskRatingResponseError(
            "AI応答がJSONとして解釈できませんでした。", raw_text=payload
        ) from exc

    if not isinstance(data, dict):
        raise MalformedRiskRatingResponseError(
            "AI応答のトップレベルが辞書ではありません。", raw_text=payload
        )

    process_name = str(data.get("工程名", "")).strip()
    process_function = str(data.get("工程の機能", "")).strip()
    entries = data.get("評価結果")
    if not isinstance(entries, list) or not entries:
        raise MalformedRiskRatingResponseError(
            "AI応答に評価結果が見つかりませんでした。", raw_text=payload
        )

    records: list[RiskRatingRecord] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise MalformedRiskRatingResponseError(
                "評価結果の形式が不正です。", raw_text=payload
            )
        rating_id = str(entry.get("行ID", "")).strip()
        if not rating_id:
            raise MalformedRiskRatingResponseError(
                "評価結果に行IDが含まれていません。", raw_text=payload
            )

        # Validate required fields exist before conversion
        for required_field in ["影響度合", "発生度合", "検出度合"]:
            if required_field not in entry or entry.get(required_field) is None:
                detail = (
                    f"評価結果に{required_field}が含まれていません。(行ID: {rating_id})"
                )
                raise MalformedRiskRatingResponseError(detail, raw_text=payload)

        try:
            impact = int(entry["影響度合"])
            occurrence = int(entry["発生度合"])
            detection = int(entry["検出度合"])
        except (TypeError, ValueError) as exc:
            raise MalformedRiskRatingResponseError(
                "影響度合・発生度合・検出度合の値が整数として解析できません。",
                raw_text=payload,
            ) from exc

        for score_value, label in (
            (impact, "影響度合"),
            (occurrence, "発生度合"),
            (detection, "検出度合"),
        ):
            if score_value < 1 or score_value > 10:
                raise MalformedRiskRatingResponseError(
                    f"{label} の値が 1〜10 の範囲外です: {score_value}",
                    raw_text=payload,
                )
        rationale = str(entry.get("根拠", "")).strip()
        impact_reason = str(entry.get("影響度合の理由", "")).strip()
        occurrence_reason = str(entry.get("発生度合の理由", "")).strip()
        detection_reason = str(entry.get("検出度合の理由", "")).strip()
        records.append(
            RiskRatingRecord(
                rating_id=rating_id,
                impact=impact,
                occurrence=occurrence,
                detection=detection,
                rationale=rationale,
                impact_reason=impact_reason,
                occurrence_reason=occurrence_reason,
                detection_reason=detection_reason,
            )
        )

    return process_name, process_function, tuple(records)


_MALFORMED_RETRY_DELAY_SECONDS = RetryPolicies.MALFORMED_RECOVERY.base_delay
_MALFORMED_RECOVERY_ATTEMPTS = RetryPolicies.MALFORMED_RECOVERY.max_attempts


def _log_malformed_response(
    group: RiskRatingGroup, exc: MalformedRiskRatingResponseError, *, attempt_label: str
) -> None:
    preview = exc.raw_text.replace("\n", "\\n")[:200]
    logger.warning(
        (
            "PFMEA risk rating JSON解析に失敗しました "
            "(group_id=%s, process=%s, attempt=%s, error=%s, preview=%s)"
        ),
        group.group_id,
        group.process_name or "(工程名未設定)",
        attempt_label,
        exc,
        preview,
    )


# =============================================================================
# Async versions for LangGraph integration
# =============================================================================


async def aevaluate_risk_group(
    model: Any,
    group: RiskRatingGroup,
    *,
    retry_policy: llm_gateway.RetryPolicy | None = None,
    executor: LLMExecutor | None = None,
) -> RiskRatingResponse:
    """非同期版リスク評価グループ処理。"""
    prompt = await _abuild_prompt(group)
    policy = retry_policy or RetryPolicies.STANDARD
    generation_config = build_generation_config(
        temperature=0.1,
        top_p=0.9,
    )
    runner = executor or LLMExecutor(model, operation_name="llm_pfmea_risk_rating")
    result = await runner.agenerate(
        prompt=prompt,
        generation_config=generation_config,
        retry_policy=policy,
        response_mime_type="application/json",
        response_schema=RISK_RATING_SCHEMA,
        metadata={
            "group_id": group.group_id,
            "process_name": group.process_name,
            "process_function": group.process_function,
            "rows": len(group.rows),
            "change_groups": len(group.change_summaries),
            "baseline_provided": bool(group.baseline_examples),
        },
    )
    if result.status != "success":
        message = result.message or "リスク評価の実行に失敗しました。"
        raise RiskRatingError(message)

    content = (result.content or "").strip()
    if not content:
        raise MalformedRiskRatingResponseError(
            "AI応答が空でした。", raw_text=result.content or ""
        )

    process_name, process_function, records = _parse_risk_rating_payload(content)
    logger.debug(
        "PFMEA risk rating completed (group_id=%s, process=%s, rows=%d)",
        group.group_id,
        process_name or group.process_name,
        len(records),
    )
    return RiskRatingResponse(
        group_id=group.group_id,
        records=records,
        raw_text=result.content or "",
    )


async def _arecover_malformed_group(
    runner: LLMExecutor,
    model: Any,
    group: RiskRatingGroup,
    *,
    retry_policy: llm_gateway.RetryPolicy | None,
    attempts: int,
) -> tuple[str, tuple[RiskRatingRecord, ...]]:
    """非同期版マルフォームリカバリー。"""
    for attempt in range(1, attempts + 1):
        await asyncio.sleep(_MALFORMED_RETRY_DELAY_SECONDS * attempt)
        try:
            response = await aevaluate_risk_group(
                model,
                group,
                retry_policy=retry_policy,
                executor=runner,
            )
            return response.group_id, response.records
        except MalformedRiskRatingResponseError as exc:
            _log_malformed_response(
                group,
                exc,
                attempt_label=f"recovery-{attempt}",
            )
            if attempt == attempts:
                raise
    raise RiskRatingError(
        f"リスク評価のリカバリー処理が想定外に終了しました（group_id={group.group_id}）。"
    )


async def aevaluate_risk_ratings(
    model: Any,
    groups: Iterable[RiskRatingGroup],
    *,
    retry_policy: llm_gateway.RetryPolicy | None = None,
    max_concurrency: int = 4,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Mapping[str, RiskRatingRecord]:
    """非同期版リスク評価バッチ処理。asyncio.gather を使用して並列実行する。

    Args:
        model: LangChain BaseChatModel インスタンス
        groups: 評価対象のリスク評価グループ
        retry_policy: リトライポリシー
        max_concurrency: 最大並列数 (Semaphore で制御)
        progress_callback: 進捗コールバック

    Returns:
        グループID:行ID ごとの評価結果
    """
    group_list = list(groups)
    if not group_list:
        return {}

    runner = LLMExecutor(model, operation_name="llm_pfmea_risk_rating")
    breaker = get_global_breaker()
    semaphore = asyncio.Semaphore(max_concurrency)
    total_groups = len(group_list)
    completed_groups = 0
    mapping: dict[str, RiskRatingRecord] = {}

    async def _task(group: RiskRatingGroup) -> tuple[str, tuple[RiskRatingRecord, ...]]:
        nonlocal completed_groups
        async with semaphore:
            try:
                response = await aevaluate_risk_group(
                    model,
                    group,
                    retry_policy=retry_policy,
                    executor=runner,
                )
                breaker.record_success()
                result = (response.group_id, response.records)
            except MalformedRiskRatingResponseError as exc:
                breaker.record_failure(is_rate_limit=False, message=str(exc))
                _log_malformed_response(group, exc, attempt_label="async-initial")
                try:
                    result = await _arecover_malformed_group(
                        runner,
                        model,
                        group,
                        retry_policy=retry_policy,
                        attempts=_MALFORMED_RECOVERY_ATTEMPTS,
                    )
                except MalformedRiskRatingResponseError as final_exc:
                    raise RiskRatingError(
                        "リスク評価の実行に失敗しました: "
                        f"{group.group_id} の応答を解析できませんでした。"
                    ) from final_exc
            except RiskRatingError as exc:
                is_rate_limit = LLMExecutor.is_rate_limit_message(str(exc))
                breaker.record_failure(is_rate_limit=is_rate_limit, message=str(exc))
                raise

            if progress_callback is not None:
                completed_groups += 1
                with contextlib.suppress(Exception):
                    progress_callback(completed_groups, total_groups)

            return result

    tasks = [_task(group) for group in group_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, BaseException):
            raise res
        group_id, records = res
        for record in records:
            mapping[f"{group_id}:{record.rating_id}"] = record

    return mapping


__all__ = [
    "MalformedRiskRatingResponseError",
    "RiskRatingError",
    "RiskRatingGroup",
    "RiskRatingRecord",
    "RiskRatingResponse",
    "RiskRatingRow",
    "aevaluate_risk_group",
    "aevaluate_risk_ratings",
]
