from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

from src.services.pfmea_context import PfmeaContext

PFMEA_COLUMN_ORDER: list[str] = [
    "区分",
    "工程名",
    "工程の機能",
    "製造保証項目",
    "要求事項（良品条件）",
    "工程故障モード",
    "故障の影響",
    "故障の原因およびメカニズム",
    "影響度合",
    "発生度合",
    "検出度合",
    "重要度（RPN）",
    "予防",
    "検出方法",
    "推奨処置",
    "工程票反映",
    "責任部署",
    "備考",
    "追加理由",
    "自信度",
    "RPN評価理由",
    "評価根拠",
    "判断",
]

# 数値型として保持すべき列（文字列化しない）
NUMERIC_COLUMNS: list[str] = [
    "自信度",
    "影響度合",
    "発生度合",
    "検出度合",
    "重要度（RPN）",
]

HIDDEN_COLUMNS = {
    "区分",
    "予防",
    "検出方法",
    "推奨処置",
    "工程票反映",
    "責任部署",
    "備考",
    "評価根拠",
    "判断",
    "追加検討ID",
}

DISPLAY_COLUMNS: list[str] = [
    column for column in PFMEA_COLUMN_ORDER if column not in HIDDEN_COLUMNS
]

# DITTO_COLUMNS: 数値列は型保持を優先し、〃記号による省略対象から除外
DITTO_COLUMNS: list[str] = [
    column
    for column in DISPLAY_COLUMNS
    if column not in NUMERIC_COLUMNS and column != "重要度（RPN）"
]

PFMEA_AI_LABEL = "AI提案"

PFMEA_EXISTING_COLUMN_MAP: dict[str, str] = {
    "process_name": "工程名",
    "process_detail": "工程の機能",
    "manufacturing_assurance": "製造保証項目",
    "requirement": "要求事項（良品条件）",
    "failure_mode": "工程故障モード",
    "effect": "故障の影響",
    "cause": "故障の原因およびメカニズム",
    "prevention": "予防",
    "detection_control": "検出方法",
    "detection": "検出度合",
    "severity": "影響度合",
    "occurrence": "発生度合",
    "recommended_action": "推奨処置",
    "process_sheet_reflection": "工程票反映",
    "responsible_department": "責任部署",
    "remarks": "備考",
    "current_control": "予防",
    "rpn": "重要度（RPN）",
    "judgement": "判断",
}

PFMEA_AI_COLUMN_MAP: dict[str, str] = {
    "追加検討ID": "追加検討ID",
    "工程名": "工程名",
    "機能": "工程の機能",
    "製造保証項目": "製造保証項目",
    "要求事項（良品条件）": "要求事項（良品条件）",
    "工程故障モード": "工程故障モード",
    "故障の影響": "故障の影響",
    "故障の原因およびメカニズム": "故障の原因およびメカニズム",
    "予防": "予防",
    "検出方法": "検出方法",
    "検出": "検出度合",
    "推奨処置": "推奨処置",
    "工程票反映": "工程票反映",
    "責任者": "責任部署",
    "備考": "備考",
    "RPN": "重要度（RPN）",
    "影響度合": "影響度合",
    "発生度合": "発生度合",
    "検出度合": "検出度合",
    "RPN評価理由": "RPN評価理由",
    "評価根拠": "評価根拠",
    "判断": "判断",
    "追加理由": "追加理由",
    "自信度": "自信度",
}


def split_function_and_assurance(
    raw_text: str, fallback_assurance: str = ""
) -> tuple[str, str]:
    if not raw_text:
        return "", fallback_assurance.strip()

    text = str(raw_text).strip()
    markers = {
        "function": "【工程の機能】",
        "assurance": "【製造保証項目】",
    }

    has_function_marker = markers["function"] in text
    has_assurance_marker = markers["assurance"] in text

    def _segment(marker: str) -> str | None:
        idx = text.find(marker)
        if idx == -1:
            return None
        start = idx + len(marker)
        candidates: list[int] = []
        for other in markers.values():
            if other == marker:
                continue
            other_idx = text.find(other, start)
            if other_idx != -1:
                candidates.append(other_idx)
        repeat_idx = text.find(marker, start)
        if repeat_idx != -1:
            candidates.append(repeat_idx)
        end = min(candidates) if candidates else len(text)
        return text[start:end].strip()

    function_text = _segment(markers["function"]) or ""
    assurance_text = _segment(markers["assurance"])

    if not has_function_marker:
        function_text = text.strip()

    if assurance_text is None:
        assurance_text = fallback_assurance.strip()
    else:
        assurance_text = assurance_text.replace(markers["assurance"], "").strip()
    if not has_assurance_marker and not assurance_text:
        assurance_text = fallback_assurance.strip()

    return function_text, assurance_text


def normalize_existing_pfmea(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=PFMEA_COLUMN_ORDER)

    working = df.copy()
    working = working.rename(columns=PFMEA_EXISTING_COLUMN_MAP)
    working = working.loc[:, ~working.columns.duplicated(keep="first")]

    preserved_columns = {
        "mapped_function",
        "mapped_assurance",
        "mapping_reason",
        "mapping_error",
    }
    columns = list(working.columns)
    for column in columns:
        if column not in PFMEA_COLUMN_ORDER and column not in preserved_columns:
            working = working.drop(columns=[column])

    mapped_function_series = working.get("mapped_function")
    mapped_assurance_series = working.get("mapped_assurance")
    mapping_reason_series = working.get("mapping_reason")

    if (
        mapped_function_series is not None
        and mapped_function_series.astype(str).str.strip().any()
    ):
        working["工程の機能"] = mapped_function_series.astype(str).fillna("")
        if mapped_assurance_series is not None:
            working["製造保証項目"] = mapped_assurance_series.astype(str).fillna("")
        if mapping_reason_series is not None:
            working["追加理由"] = mapping_reason_series.astype(str).fillna("")
    elif "工程の機能" in working.columns:

        def _split_row(row: pd.Series) -> pd.Series:
            raw = row.get("工程の機能", "")
            fallback = row.get("製造保証項目", "")
            function_text, assurance_text = split_function_and_assurance(
                str(raw) if raw is not None else "",
                str(fallback) if fallback is not None else "",
            )
            return pd.Series(
                {"工程の機能": function_text, "製造保証項目": assurance_text}
            )

        extracted = working.apply(_split_row, axis=1)
        working["工程の機能"] = extracted["工程の機能"]
        working["製造保証項目"] = extracted["製造保証項目"]

    working = working.drop(
        columns=["mapped_function", "mapped_assurance", "mapping_reason"],
        errors="ignore",
    )

    working["区分"] = "既存PFMEA"
    for column in PFMEA_COLUMN_ORDER:
        if column not in working.columns:
            working[column] = ""
    ordered = working.loc[:, PFMEA_COLUMN_ORDER]

    # 数値列を保存してから文字列化
    numeric_values = {}
    for col in NUMERIC_COLUMNS:
        if col in ordered.columns:
            numeric_values[col] = (
                pd.to_numeric(ordered[col], errors="coerce").fillna(0).astype(int)
            )

    ordered = ordered.fillna("").astype(str)

    # 数値列を復元
    for col, values in numeric_values.items():
        ordered[col] = values

    ffill_columns = [
        "工程名",
        "工程の機能",
        "製造保証項目",
        "要求事項（良品条件）",
    ]
    for column in ffill_columns:
        if column in ordered.columns:
            series = ordered[column].replace({"": pd.NA}).ffill()
            ordered[column] = series.fillna("")

    return ordered


def _normalize_confidence_value(raw_value: str, default: int = 3) -> int:
    """自信度値を正規化（1-5の範囲に制限）。

    Args:
        raw_value: LLMが出力した自信度値（文字列）
        default: 範囲外または無効な値の場合のデフォルト値

    Returns:
        1-5の範囲に制限された整数値
    """
    try:
        value = int(str(raw_value).strip())
        if 1 <= value <= 5:
            return value
        return default
    except (ValueError, TypeError):
        return default


def normalize_ai_pfmea(rows: Sequence[Mapping[str, str]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=PFMEA_COLUMN_ORDER)

    ai_df = pd.DataFrame(rows)
    if ai_df.empty:
        return pd.DataFrame(columns=PFMEA_COLUMN_ORDER)

    ai_df = ai_df.rename(columns=PFMEA_AI_COLUMN_MAP)
    ai_df = ai_df.loc[:, ~ai_df.columns.duplicated(keep="first")]

    # 自信度のバリデーション（1-5の範囲に制限）
    if "自信度" in ai_df.columns:
        ai_df["自信度"] = ai_df["自信度"].apply(_normalize_confidence_value)

    def _split_ai(row: pd.Series) -> pd.Series:
        raw_function = row.get("工程の機能", "")
        fallback_assurance = row.get("製造保証項目", "")
        function_text, assurance_text = split_function_and_assurance(
            str(raw_function) if raw_function is not None else "",
            str(fallback_assurance) if fallback_assurance is not None else "",
        )
        return pd.Series({"工程の機能": function_text, "製造保証項目": assurance_text})

    if "工程の機能" in ai_df.columns:
        split_df = ai_df.apply(_split_ai, axis=1)
        ai_df["工程の機能"] = split_df["工程の機能"]
        ai_df["製造保証項目"] = split_df["製造保証項目"]

    for column in PFMEA_COLUMN_ORDER:
        if column not in ai_df.columns:
            ai_df[column] = ""

    ai_df["区分"] = PFMEA_AI_LABEL
    ordered = ai_df.loc[:, PFMEA_COLUMN_ORDER]

    # 数値列を保存してから文字列化
    numeric_values = {}
    for col in NUMERIC_COLUMNS:
        if col in ordered.columns:
            numeric_values[col] = (
                pd.to_numeric(ordered[col], errors="coerce").fillna(0).astype(int)
            )

    result = ordered.fillna("").astype(str)

    # 数値列を復元
    for col, values in numeric_values.items():
        result[col] = values

    return result


def build_pfmea_ai_tables(
    context: PfmeaContext | None,
    ai_rows: Sequence[Mapping[str, str]],
    *,
    default_block: str | None = None,
) -> OrderedDict[str, pd.DataFrame]:
    tables: OrderedDict[str, pd.DataFrame] = OrderedDict()

    existing_df = context.data if context is not None else None
    existing_tables: dict[str, pd.DataFrame] = {}
    if existing_df is not None and not existing_df.empty:
        working = existing_df.copy()
        block_column = None
        for candidate in ("block", "ブロック", "PFMEAブロック"):
            if candidate in working.columns:
                block_column = working.pop(candidate)
                break
        if block_column is None:
            fallback_block = (
                context.block
                if context is not None and context.block
                else default_block
            )
            block_column = pd.Series(
                [fallback_block or "未分類ブロック"] * len(working),
                dtype=str,
            )
        else:
            fallback = (
                (context.block if context is not None else None)
                or default_block
                or "未分類ブロック"
            )
            block_column = block_column.fillna(fallback)

        working["_pfmea_block"] = block_column.astype(str)
        for block_label, block_df in working.groupby("_pfmea_block"):
            normalized = normalize_existing_pfmea(
                block_df.drop(columns=["_pfmea_block"])
            )
            if not normalized.empty:
                existing_tables[str(block_label)] = normalized

    ai_tables: dict[str, pd.DataFrame] = {}
    if ai_rows:
        rows_by_block: dict[str, list[Mapping[str, str]]] = {}
        fallback_block = (
            context.block if context is not None and context.block else default_block
        )
        for row in ai_rows:
            block_label = row.get("ブロック") or fallback_block or "未分類ブロック"
            rows_by_block.setdefault(str(block_label), []).append(row)
        for block_label, records in rows_by_block.items():
            normalized_ai = normalize_ai_pfmea(records)
            if not normalized_ai.empty:
                ai_tables[str(block_label)] = normalized_ai

    combined_blocks = set(existing_tables.keys()) | set(ai_tables.keys())
    for block_label in sorted(combined_blocks):
        existing_block_df = existing_tables.get(
            block_label, pd.DataFrame(columns=PFMEA_COLUMN_ORDER)
        )
        ai_block_df = ai_tables.get(
            block_label, pd.DataFrame(columns=PFMEA_COLUMN_ORDER)
        )
        frames: list[pd.DataFrame] = []
        if not existing_block_df.empty:
            frames.append(existing_block_df)
        if not ai_block_df.empty:
            frames.append(ai_block_df)
        if not frames:
            continue
        concatenated = pd.concat(frames, ignore_index=True)
        tables[block_label] = (
            concatenated.loc[:, PFMEA_COLUMN_ORDER].fillna("").astype(str)
        )

    return tables


def aggregate_pfmea_results(
    changes: Sequence[Any],
    pfmea_context: Mapping[str, PfmeaContext | None],
    rows_by_change: Mapping[str, Sequence[Mapping[str, str]]],
    *,
    block_order: Iterable[str] = (),
    ditto_columns: Iterable[str] | None = None,
) -> OrderedDict[str, pd.DataFrame]:
    aggregated_existing: dict[str, pd.DataFrame] = {}
    aggregated_ai: dict[str, pd.DataFrame] = {}
    ditto_targets = list(ditto_columns or [])

    for change in changes:
        change_id = getattr(change, "change_id", "")
        context_bundle = pfmea_context.get(change_id)
        rows = rows_by_change.get(change_id, [])
        tables_by_block = build_pfmea_ai_tables(
            context_bundle,
            rows,
            default_block=getattr(change, "block", None),
        )
        for block_label, table_df in tables_by_block.items():
            block_label = str(block_label)
            if table_df.empty:
                continue
            existing_rows = table_df[table_df["区分"] != PFMEA_AI_LABEL]
            ai_rows = table_df[table_df["区分"] == PFMEA_AI_LABEL]
            if not existing_rows.empty and block_label not in aggregated_existing:
                aggregated_existing[block_label] = existing_rows.loc[
                    :, PFMEA_COLUMN_ORDER
                ]
            if not ai_rows.empty:
                if block_label in aggregated_ai:
                    aggregated_ai[block_label] = pd.concat(
                        [
                            aggregated_ai[block_label],
                            ai_rows.loc[:, PFMEA_COLUMN_ORDER],
                        ],
                        ignore_index=True,
                    )
                else:
                    aggregated_ai[block_label] = ai_rows.loc[:, PFMEA_COLUMN_ORDER]

    block_sequence: list[str] = []
    seen = set()
    for block in block_order:
        if block in aggregated_existing or block in aggregated_ai:
            block_sequence.append(block)
            seen.add(block)
    for block in sorted(set(aggregated_existing.keys()) | set(aggregated_ai.keys())):
        if block not in seen:
            block_sequence.append(block)
            seen.add(block)

    result: OrderedDict[str, pd.DataFrame] = OrderedDict()
    for block_label in block_sequence:
        existing_df = aggregated_existing.get(block_label)
        ai_df = aggregated_ai.get(block_label)
        if (existing_df is None or existing_df.empty) and (
            ai_df is None or ai_df.empty
        ):
            continue

        group_columns = ("工程名", "工程の機能")

        def _group_key(
            row: pd.Series, columns: tuple[str, str] = group_columns
        ) -> tuple[str, str]:
            col1, col2 = columns
            return str(row.get(col1, "")).strip(), str(row.get(col2, "")).strip()

        ordered_rows: list[dict[str, Any]] = []
        ai_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        ai_key_order: list[tuple[str, str]] = []

        if ai_df is not None and not ai_df.empty:
            for _, ai_row in ai_df.iterrows():
                key = _group_key(ai_row)
                if key not in ai_by_key:
                    ai_by_key[key] = []
                    ai_key_order.append(key)
                ai_by_key[key].append(ai_row.to_dict())

        if existing_df is not None and not existing_df.empty:
            for _, existing_row in existing_df.iterrows():
                ordered_rows.append(existing_row.to_dict())
                key = _group_key(existing_row)
                if key in ai_by_key:
                    ordered_rows.extend(ai_by_key.pop(key))

        for key in ai_key_order:
            leftover = ai_by_key.get(key)
            if leftover:
                ordered_rows.extend(leftover)

        concatenated = pd.DataFrame(ordered_rows or [], columns=PFMEA_COLUMN_ORDER)
        if concatenated.empty and ai_df is not None and not ai_df.empty:
            concatenated = ai_df.copy()

        # 数値列を保存してから文字列化
        numeric_values = {}
        for col in NUMERIC_COLUMNS:
            if col in concatenated.columns:
                numeric_values[col] = (
                    pd.to_numeric(concatenated[col], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

        concatenated = concatenated.drop_duplicates().fillna("").astype(str)

        # 数値列を復元
        for col, values in numeric_values.items():
            concatenated[col] = values

        if ditto_targets:
            block_series = concatenated.get("ブロック")
            block_values = (
                block_series.astype(str).tolist()
                if block_series is not None
                else [""] * len(concatenated)
            )
            for column in ditto_targets:
                if column not in concatenated.columns:
                    continue
                previous_value: str | None = None
                previous_block: str | None = None
                normalized_values: list[str] = []
                for raw_value, block in zip(
                    concatenated[column].tolist(), block_values
                ):
                    value = "" if raw_value is None else str(raw_value).strip()
                    if (
                        previous_value is not None
                        and previous_block == block
                        and value
                        and value == previous_value
                    ):
                        normalized_values.append("〃")
                    else:
                        normalized_values.append(value)
                        if value:
                            previous_value = value
                            previous_block = block
                concatenated[column] = normalized_values
        result[block_label] = concatenated.loc[:, PFMEA_COLUMN_ORDER]

    return result


__all__ = [
    "DITTO_COLUMNS",
    "DISPLAY_COLUMNS",
    "HIDDEN_COLUMNS",
    "PFMEA_AI_LABEL",
    "PFMEA_COLUMN_ORDER",
    "PFMEA_EXISTING_COLUMN_MAP",
    "PFMEA_AI_COLUMN_MAP",
    "split_function_and_assurance",
    "normalize_existing_pfmea",
    "normalize_ai_pfmea",
    "build_pfmea_ai_tables",
    "aggregate_pfmea_results",
]
