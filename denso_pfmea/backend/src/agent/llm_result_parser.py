"""Helpers for parsing LLM outputs into structured rows and rating targets."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from src.services.pfmea_ai import split_function_and_assurance

logger = logging.getLogger(__name__)

# Expected headers for LLM JSON output
EXPECTED_LLM_HEADERS: Tuple[str, ...] = (
    "追加検討ID",
    "工程名",
    "機能",
    "製造保証項目",
    "要求事項（良品条件）",
    "工程故障モード",
    "故障の影響",
    "故障の原因およびメカニズム",
    "追加理由",
    "自信度",
    "判断",
    "評価根拠",
)


@dataclass(frozen=True)
class RatingTarget:
    """Intermediate representation for risk rating requests."""

    change: Any
    change_id: str
    row: Dict[str, str]
    rating_id: str
    process_name: str
    function_text: str
    assurances: Tuple[str, ...]
    group_id: str


@dataclass(frozen=True)
class ParsedChangeResult:
    """Parsed result for a single change entry."""

    processed_entry: Dict[str, Any]
    rows: List[Dict[str, str]]
    rating_targets: List[RatingTarget]


def parse_json_response(
    content: str,
) -> Tuple[List[Dict[str, str]] | None, str | None]:
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
    rows: List[Dict[str, str]] = []
    row_errors: List[str] = []

    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            row_errors.append(f"{idx}行目: オブジェクトではありません")
            continue

        row: Dict[str, str] = {}
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

        rows.append(row)

    error_message = "\n".join(row_errors) if row_errors else None
    return rows, error_message


def _verify_consistency(row: Mapping[str, str]) -> List[str]:
    """Run lightweight consistency checks for CoVe-style validation."""
    warnings: List[str] = []

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


def parse_change_entry(
    change: Any,
    entry: Mapping[str, Any] | None,
    expected_rows: Sequence[str] | None = None,
) -> ParsedChangeResult:
    """Parse a single LLM batch entry."""
    change_id = (
        getattr(change, "change_id", "")
        if hasattr(change, "change_id")
        else change.get("change_id", "")
    )
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

    # Parse JSON response
    json_rows, parse_error = parse_json_response(content)
    if json_rows is None:
        return ParsedChangeResult(
            processed_entry={
                "status": "error",
                "content": content,
                "message": parse_error or "AI推定結果の解析に失敗しました。",
            },
            rows=[],
            rating_targets=[],
        )

    rows = json_rows
    rating_targets: List[RatingTarget] = []
    row_refs: List[Dict[str, str]] = []
    consistency_warnings: List[str] = []

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


def split_assurance_values(raw_text: str) -> Tuple[str, ...]:
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
    notes: List[str] = []
    for key in ("工程票反映", "備考", "評価根拠"):
        value = str(row.get(key, "") or "").strip()
        if value:
            notes.append(f"{key}:{value}")
    return " / ".join(notes)


def format_variant_metadata(metadata: Mapping[str, Mapping[str, str]]) -> List[str]:
    """Format variant metadata for display."""
    lines: List[str] = []
    for scope, payload in metadata.items():
        entries = [f"{key}={value}" for key, value in payload.items() if value]
        if entries:
            lines.append(f"  {scope}: " + " / ".join(entries))
    return lines


def summarize_change_metadata(change: Any, rows: Sequence[Any] | None = None) -> str:
    """Summarize change metadata for risk rating context."""

    # Handle both dict and object-like change
    def _get(name: str, default: Any = "") -> Any:
        if isinstance(change, dict):
            return change.get(name, default)
        return getattr(change, name, default)

    base: List[str] = [
        f"- 変化ID {_get('change_id', '(不明)')}: "
        f"バリエーション={_get('variant_id', '―')} / "
        f"ブロック={_get('block', '―')} / "
        f"ステーション={_get('station', '―')}"
    ]
    change_type = str(_get("change_type", "") or "")
    if change_type:
        base.append(f"  変更種別: {change_type}")
    part_label = str(_get("part_label", "") or "")
    if part_label:
        base.append(f"  対象部品: {part_label}")
    original_part = str(
        _get("original_part_label", "") or _get("original_value", "") or ""
    )
    updated_part = str(_get("updated_part_label", "") or _get("new_value", "") or "")
    if original_part or updated_part:
        base.append(f"  流用元={original_part or '―'} / 変更後={updated_part or '―'}")
    shape_feature = str(_get("shape_feature", "") or "")
    if shape_feature:
        base.append(f"  形状特長: {shape_feature}")
    keywords_raw = _get("keywords", [])
    keywords: List[str] = (
        list(keywords_raw) if isinstance(keywords_raw, (list, tuple)) else []
    )
    if keywords:
        base.append(f"  キーワード: {', '.join(keywords)}")
    variant_metadata_raw = _get("variant_metadata", {})
    variant_metadata: Mapping[str, Mapping[str, str]] = (
        variant_metadata_raw if isinstance(variant_metadata_raw, Mapping) else {}
    )
    base.extend(format_variant_metadata(variant_metadata))

    if rows:
        for row in rows:
            if isinstance(row, dict):
                base.append(
                    "  候補: "
                    f"要求事項={row.get('requirement', '―') or '―'} / "
                    f"故障モード={row.get('failure_mode', '―') or '―'} / "
                    f"影響={row.get('effect', '―') or '―'}"
                )
            else:
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
    "split_assurance_values",
    "make_group_id",
    "compose_additional_notes",
    "format_variant_metadata",
    "summarize_change_metadata",
]
