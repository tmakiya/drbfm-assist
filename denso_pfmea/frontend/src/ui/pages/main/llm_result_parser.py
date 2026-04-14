"""Helpers for parsing LLM outputs into structured rows and rating targets."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.services.pfmea_ai import split_function_and_assurance

from .constants import EXPECTED_LLM_HEADERS
from .llm_results_renderer import parse_llm_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RatingTarget:
    """Intermediate representation for risk rating requests."""

    change: Any
    change_id: str
    row: dict[str, str]
    rating_id: str
    process_name: str
    function_text: str
    assurances: tuple[str, ...]
    group_id: str


@dataclass(frozen=True)
class ParsedChangeResult:
    """Parsed result for a single change entry."""

    processed_entry: dict[str, Any]
    rows: list[dict[str, str]]
    rating_targets: list[RatingTarget]


def parse_json_response(
    content: str,
) -> tuple[list[dict[str, str]] | None, str | None]:
    """Parse JSON response from Structured Output.

    Args:
        content: Raw JSON string from LLM response.

    Returns:
        Tuple of (rows, error_message).
        - On success: (list of row dicts, None)
        - On failure: (None, error_message)
    """
    if not content:
        return None, "AI応答が空でした。"

    # JSON文字列の前後の余分な文字を除去
    content = content.strip()

    # ```json ... ``` ブロックが含まれている場合は抽出
    json_match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
    if json_match:
        content = json_match.group(1).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error: %s", exc)
        return None, f"AI応答をJSONとして解析できませんでした: {exc}"

    # results 配列を抽出
    if isinstance(data, dict):
        results = data.get("results", [])
    elif isinstance(data, list):
        results = data
    else:
        return None, "AI応答の形式が不正です（オブジェクトまたは配列が必要）。"

    if not results:
        return None, "AI応答の results が空でした。"

    # 各行を正規化
    rows: list[dict[str, str]] = []
    row_errors: list[str] = []

    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            row_errors.append(f"{idx}行目: オブジェクトではありません")
            continue

        row: dict[str, str] = {}
        for header in EXPECTED_LLM_HEADERS:
            value = item.get(header, "")
            if value is None:
                value = ""
            # 数値型の場合は文字列に変換
            if isinstance(value, (int, float)):
                value = str(int(value)) if isinstance(value, int) else str(value)
            else:
                value = str(value).strip()
            # <br> タグを改行に正規化
            value = (
                value.replace("<br>", "\n")
                .replace("<br/>", "\n")
                .replace("<br />", "\n")
            )
            row[header] = value

        # 必須フィールドの検証
        missing_fields = [h for h in EXPECTED_LLM_HEADERS if not row.get(h)]
        if missing_fields:
            row_errors.append(
                f"{idx}行目: 必須フィールドが欠落({', '.join(missing_fields[:3])})"
            )

        rows.append(row)

    error_message = "\n".join(row_errors) if row_errors else None
    return rows, error_message


def _verify_consistency(row: Mapping[str, str]) -> list[str]:
    """Run lightweight consistency checks for CoVe-style validation."""
    warnings: list[str] = []

    judgement = str(row.get("判断", "") or "").strip()
    reason = str(row.get("追加理由", "") or "").strip()
    confidence_raw = str(row.get("自信度", "") or "").strip()
    try:
        confidence = int(confidence_raw)
    except (TypeError, ValueError):
        confidence = -1

    if confidence == 1 and judgement == "追加推奨":
        warnings.append("自信度=1 かつ 判断=追加推奨 は矛盾の可能性あり")
    if confidence == 5 and len(reason) < 20:
        warnings.append("自信度=5 だが追加理由が短い")
    if confidence < 1 or confidence > 5:
        warnings.append(f"自信度が範囲外: {confidence_raw}")

    return warnings


def _is_json_response(content: str) -> bool:
    """Check if the content appears to be JSON format."""
    content = content.strip()
    # JSON オブジェクトまたは配列で始まる場合
    if content.startswith("{") or content.startswith("["):
        return True
    # ```json ブロックが含まれている場合
    return "```json" in content


def parse_change_entry(
    change: Any,
    entry: Mapping[str, Any] | None,
    expected_rows: Sequence[str],
) -> ParsedChangeResult:
    """Parse a single LLM batch entry."""
    change_id = getattr(change, "change_id", "")
    empty_result = ParsedChangeResult(
        processed_entry={
            "status": "error",
            "content": "",
            "message": "AI推定結果を取得できませんでした。",
        },
        rows=[],
        rating_targets=[],
    )

    if entry is None:
        return empty_result

    status = entry.get("status")
    if status != "success":
        return ParsedChangeResult(
            processed_entry=dict(entry),
            rows=[],
            rating_targets=[],
        )

    content = entry.get("content", "")

    # JSON 形式の応答を優先的に処理（Structured Output）
    if _is_json_response(content):
        json_rows, json_error = parse_json_response(content)
        if json_rows is not None:
            rows = json_rows
            parse_error = json_error
        else:
            # JSON パースに失敗した場合は Markdown テーブルを試行
            logger.info("JSON parse failed, falling back to Markdown table parsing")
            table_df, parse_error = parse_llm_table(content, expected_rows)
            if table_df is None:
                return ParsedChangeResult(
                    processed_entry={
                        "status": "error",
                        "content": content,
                        "message": parse_error or "AI推定結果の解析に失敗しました。",
                    },
                    rows=[],
                    rating_targets=[],
                )
            rows = normalize_table_rows(
                table_df.to_dict("records"), EXPECTED_LLM_HEADERS
            )
    else:
        # Markdown テーブル形式の応答を処理
        table_df, parse_error = parse_llm_table(content, expected_rows)
        if table_df is None:
            return ParsedChangeResult(
                processed_entry={
                    "status": "error",
                    "content": content,
                    "message": parse_error or "AI推定結果の解析に失敗しました。",
                },
                rows=[],
                rating_targets=[],
            )
        rows = normalize_table_rows(table_df.to_dict("records"), EXPECTED_LLM_HEADERS)
    rating_targets: list[RatingTarget] = []
    row_refs: list[dict[str, str]] = []
    consistency_warnings: list[str] = []
    for idx, row in enumerate(rows):
        row_ref = dict(row)
        row_refs.append(row_ref)
        row_warnings = _verify_consistency(row_ref)
        if row_warnings:
            identifier = str(row_ref.get("追加検討ID") or f"row-{idx + 1}")
            consistency_warnings.extend(
                [f"{identifier}: {warning}" for warning in row_warnings]
            )
        raw_identifier = str(row_ref.get("追加検討ID", "") or "").strip()
        rating_id = raw_identifier or f"{change_id}-{idx + 1}"
        function_text, assurance_text = split_function_and_assurance(
            str(row_ref.get("機能", "") or ""),
            str(row_ref.get("製造保証項目", "") or ""),
        )
        assurance_source = assurance_text or str(row_ref.get("製造保証項目", "") or "")
        assurances = split_assurance_values(assurance_source)
        group_id = make_group_id(
            change_id,
            str(row_ref.get("工程名", "") or ""),
            function_text or str(row_ref.get("機能", "") or ""),
        )
        rating_targets.append(
            RatingTarget(
                change=change,
                change_id=change_id,
                row=row_ref,
                rating_id=rating_id,
                process_name=str(row_ref.get("工程名", "") or ""),
                function_text=function_text or str(row_ref.get("機能", "") or ""),
                assurances=assurances,
                group_id=group_id,
            )
        )

    if parse_error:
        processed_entry = {
            "status": "warning",
            "content": content,
            "message": parse_error,
        }
    else:
        processed_entry = dict(entry)
    if consistency_warnings:
        processed_entry["consistency_warnings"] = consistency_warnings

    return ParsedChangeResult(
        processed_entry=processed_entry,
        rows=row_refs,
        rating_targets=rating_targets,
    )


def normalize_table_rows(
    records: Sequence[Mapping[str, Any]], headers: tuple[str, ...]
) -> list[dict[str, str]]:
    """Normalize table rows by ensuring all headers exist."""
    normalized: list[dict[str, str]] = []
    for record in records:
        row: dict[str, str] = {}
        for header in headers:
            value = record.get(header, "")
            if value is None:
                text = ""
            else:
                text = str(value).strip()
                text = (
                    text.replace("<br>", "\n")
                    .replace("<br/>", "\n")
                    .replace("<br />", "\n")
                )
            row[header] = text
        normalized.append(row)
    return normalized


def merge_change_metadata(change: Any, row: Mapping[str, str]) -> dict[str, str]:
    """Merge change metadata with parsed row information."""
    payload = {
        "バリエーション": getattr(change, "variant_id", ""),
        "ブロック": getattr(change, "block", ""),
        "ステーション": getattr(change, "station", ""),
        "対象部品": getattr(change, "part_label", ""),
        "変更種別": getattr(change, "change_type", ""),
    }
    merged = {**payload, **row}
    return {
        key: ("" if value is None else str(value).strip())
        for key, value in merged.items()
    }


def split_assurance_values(raw_text: str) -> tuple[str, ...]:
    """Split manufacturing assurance text into individual items."""
    text = (raw_text or "").strip()
    if not text:
        return ()
    fragments = re.split(r"[・\n\r]+", text)
    cleaned = tuple(item.strip() for item in fragments if item.strip())
    return cleaned


def make_group_id(change_id: str, process_name: str, function_text: str) -> str:
    """Generate a stable group identifier for risk rating."""
    key = "|".join(
        [
            change_id.strip(),
            (process_name or "").strip(),
            (function_text or "").strip(),
        ]
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"{change_id}:{digest}"


def compose_additional_notes(row: Mapping[str, str]) -> str:
    """Compose additional notes string from multiple fields."""
    notes: list[str] = []
    for key in ("工程票反映", "備考", "評価根拠"):
        value = str(row.get(key, "") or "").strip()
        if value:
            notes.append(f"{key}:{value}")
    return " / ".join(notes)


def format_variant_metadata(metadata: Mapping[str, Mapping[str, str]]) -> list[str]:
    """Format variant metadata for display."""
    lines: list[str] = []
    for scope, payload in metadata.items():
        entries = [f"{key}={value}" for key, value in payload.items() if value]
        if entries:
            lines.append(f"  {scope}: " + " / ".join(entries))
    return lines


def summarize_change_metadata(change: Any, rows: Sequence[Any] | None = None) -> str:
    """Summarize change metadata for risk rating context."""
    base = [
        f"- 変化ID {getattr(change, 'change_id', '(不明)')}: "
        f"バリエーション={getattr(change, 'variant_id', '―')} / "
        f"ブロック={getattr(change, 'block', '―')} / "
        f"ステーション={getattr(change, 'station', '―')}"
    ]
    change_type = getattr(change, "change_type", "")
    if change_type:
        base.append(f"  変更種別: {change_type}")
    part_label = getattr(change, "part_label", "")
    if part_label:
        base.append(f"  対象部品: {part_label}")
    original_part = getattr(change, "original_part_label", "") or getattr(
        change, "original_value", ""
    )
    updated_part = getattr(change, "updated_part_label", "") or getattr(
        change, "new_value", ""
    )
    if original_part or updated_part:
        base.append(f"  流用元={original_part or '―'} / 変更後={updated_part or '―'}")
    shape_feature = getattr(change, "shape_feature", "")
    if shape_feature:
        base.append(f"  形状特長: {shape_feature}")
    keywords = getattr(change, "keywords", [])
    if keywords:
        base.append(f"  キーワード: {', '.join(keywords)}")
    variant_metadata = getattr(change, "variant_metadata", {}) or {}
    base.extend(format_variant_metadata(variant_metadata))

    if rows:
        for row in rows:
            base.append(
                "  候補: "
                f"要求事項={getattr(row, 'requirement', '―') or '―'} / "
                f"故障モード={getattr(row, 'failure_mode', '―') or '―'} / "
                f"影響={getattr(row, 'effect', '―') or '―'}"
            )
    return "\n".join(base)


__all__ = [
    "RatingTarget",
    "ParsedChangeResult",
    "parse_change_entry",
    "parse_json_response",
    "normalize_table_rows",
    "merge_change_metadata",
    "split_assurance_values",
    "make_group_id",
    "compose_additional_notes",
    "format_variant_metadata",
    "summarize_change_metadata",
]
