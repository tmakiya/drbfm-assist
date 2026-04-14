"""LLM results rendering components.

This module handles the display and formatting of AI inference results,
including PFMEA tables, CSV downloads, and data parsing.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import datetime
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st

from src.services.pfmea.mapping_log_export import display_mapping_log_download_button
from src.services.pfmea_ai import (
    DISPLAY_COLUMNS,
    HIDDEN_COLUMNS,
    PFMEA_AI_LABEL,
    PFMEA_COLUMN_ORDER,
    aggregate_pfmea_results,
    normalize_existing_pfmea,
)
from src.services.pfmea_context import PfmeaContext
from src.ui.design_system import responsive_table_wrapper
from src.ui.design_system.tokens import colors, shadows, spacing, typography
from src.ui.excel_styling import apply_excel_styling
from src.ui.html_sanitization import fully_sanitize_html, sanitize_dataframe_for_html
from src.ui.shared_constants import (
    ICON_INFO,
    PFMEA_BLOCKS,
)

from .constants import EXPECTED_LLM_HEADERS

# CSS styles for PFMEA result tables (using design tokens)
PFMEA_TABLE_STYLES = [
    {
        "selector": "table",
        "props": [
            ("border-collapse", "separate"),
            ("border-spacing", "0"),
            ("width", "100%"),
            ("min-width", "100%"),
            ("font-size", typography.SIZE_PX_13),
            ("font-family", typography.FONT_FAMILY_PRIMARY),
            ("table-layout", "auto"),
        ],
    },
    {
        "selector": "th, td",
        "props": [
            ("border-bottom", f"1px solid {colors.TABLE_BORDER}"),
            ("border-right", f"1px solid {colors.TABLE_BORDER}"),
            ("padding", f"{spacing.SM} {spacing.MD}"),
            ("text-align", "left"),
            ("vertical-align", "top"),
            ("word-break", "break-word"),
        ],
    },
    {
        "selector": "thead th",
        "props": [
            ("background-color", colors.TABLE_HEADER_BG),
            ("font-weight", str(typography.WEIGHT_SEMIBOLD)),
            ("position", "sticky"),
            ("top", "0"),
            ("z-index", "3"),
        ],
    },
]

PFMEA_TABLE_STYLE_BLOCK = f"""
<style>
.pfmea-ai-table-shell {{
  position: relative;
  border: 1px solid {colors.TABLE_CONTAINER_BORDER};
  border-radius: 6px;
  background: {colors.SURFACE};
  box-shadow: {shadows.CARD};
  overflow: hidden;
  margin-bottom: {spacing.MD};
}}
.pfmea-ai-table-scroll {{
  position: relative;
  max-height: 520px;
  overflow: auto;
  overscroll-behavior: contain;
}}
.pfmea-ai-table-scroll::after {{
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  width: 32px;
  height: 100%;
  pointer-events: none;
  background: linear-gradient(90deg, rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.08));
}}
.pfmea-ai-table th,
.pfmea-ai-table td {{
  background-color: {colors.SURFACE};
}}
.pfmea-ai-table thead th {{
  box-shadow: inset 0 -1px 0 {colors.TABLE_BORDER};
}}
.pfmea-ai-table tbody tr:hover td {{
  background-color: {colors.SURFACE_VARIANT};
}}
.pfmea-ai-table tbody tr:hover td:first-child {{
  background-color: {colors.SURFACE_VARIANT};
}}
.pfmea-ai-table th:first-child,
.pfmea-ai-table td:first-child {{
  position: sticky;
  left: 0;
  z-index: 2;
  min-width: 200px;
  max-width: 240px;
  box-shadow: 2px 0 0 0 {colors.TABLE_BORDER};
}}
.pfmea-ai-table thead th:first-child {{
  z-index: 4;
}}
.pfmea-ai-table th,
.pfmea-ai-table td {{
  min-width: 140px;
  max-width: 360px;
}}
.pfmea-ai-table th:nth-child(2),
.pfmea-ai-table td:nth-child(2) {{
  min-width: 220px;
  max-width: 320px;
}}
.pfmea-ai-table th:nth-child(3),
.pfmea-ai-table td:nth-child(3) {{
  min-width: 220px;
  max-width: 320px;
}}
.pfmea-ai-table th:nth-child(4),
.pfmea-ai-table td:nth-child(4) {{
  min-width: 220px;
  max-width: 320px;
}}
.pfmea-ai-table th:nth-child(5),
.pfmea-ai-table td:nth-child(5) {{
  min-width: 160px;
  max-width: 220px;
}}
.pfmea-ai-table tbody tr:nth-child(even) td {{
  background-color: {colors.TABLE_ROW_EVEN};
}}
.pfmea-ai-table tbody tr:nth-child(even) td:first-child {{
  background-color: {colors.TABLE_ROW_EVEN};
}}
@media (max-width: 900px) {{
  .pfmea-ai-table th,
  .pfmea-ai-table td {{
    font-size: {typography.SIZE_PX_12};
    padding: {spacing.XS};
  }}
  .pfmea-ai-table th:nth-child(n+6),
  .pfmea-ai-table td:nth-child(n+6) {{
    display: none;
  }}
}}
</style>
"""


# UI-only display aliases for reference columns
AI_REFERENCE_COLUMN_ALIASES: dict[str, str] = {
    "追加理由": "AI追加理由",
    "自信度": "AI自信度",
    "RPN評価理由": "AI RPN評価理由",
}


def style_pfmea_ai_dataframe(
    df: pd.DataFrame, classification: pd.Series | None = None
) -> str:
    """Apply custom styling to PFMEA AI results DataFrame.

    Highlights rows marked as AI-generated with red text color.
    Returns HTML with embedded CSS for scrollable table display.

    SECURITY: Sanitizes all DataFrame content before HTML rendering to prevent XSS.

    Args:
        df: DataFrame containing PFMEA results to display.
        classification: Optional Series indicating row classification
            (e.g., PFMEA_AI_LABEL for AI-generated rows).

    Returns:
        HTML string with styled table and container CSS (sanitized).
    """
    if df.empty:
        return ""

    # UI表示列は重要度を前方に寄せ、閲覧性を優先
    df = _reorder_display_columns(df)

    # 参照情報の列名にAI接頭辞を付与（UI表示専用）
    df = df.rename(columns=AI_REFERENCE_COLUMN_ALIASES)

    # SECURITY: Sanitize DataFrame content to prevent XSS
    df = sanitize_dataframe_for_html(df)

    if classification is None or classification.empty:
        classification_series = pd.Series([""] * len(df))
    else:
        classification_series = classification.reset_index(drop=True)

    def _row_style(row: pd.Series) -> list[str]:
        """Apply row-specific styling based on classification."""
        label = ""
        if row.name < len(classification_series):
            label = classification_series.iloc[row.name]

        if label == PFMEA_AI_LABEL or label == "〃":
            base_color = colors.PFMEA_AI_GENERATED
            styles = [f"color: {base_color}" for _ in row.index]
        else:
            base_color = colors.TEXT_PRIMARY
            styles = [f"color: {base_color}" for _ in row.index]
        return styles

    styler = df.style.apply(_row_style, axis=1)
    styler = styler.set_table_styles(PFMEA_TABLE_STYLES)
    styler = styler.set_table_attributes('class="pfmea-ai-table"')
    styler = styler.hide(axis="index")
    html = styler.to_html()

    # SECURITY: Additional sanitization of generated HTML
    html = fully_sanitize_html(html)

    # Wrap table in responsive container (single entry point from design_system)
    html = responsive_table_wrapper(html)

    wrapped_html = (
        f'<div class="pfmea-ai-table-shell pfmea-ai-table-container">'
        f'<div class="pfmea-ai-table-scroll">{html}</div>'
        f"</div>"
    )
    return PFMEA_TABLE_STYLE_BLOCK + wrapped_html


def _reorder_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    priority = [
        "工程名",
        "工程の機能",
        "工程故障モード",
        "故障の影響",
        "重要度（RPN）",
        "影響度合",
        "発生度合",
        "検出度合",
        "製造保証項目",
        "要求事項（良品条件）",
        "故障の原因およびメカニズム",
        "追加理由",
        "自信度",
        "RPN評価理由",
    ]
    ordered: list[str] = []
    for column in priority:
        if column in df.columns:
            ordered.append(column)
    for column in df.columns:
        if column not in ordered:
            ordered.append(column)
    return df.reindex(columns=ordered)


def parse_llm_table(
    markdown: str, expected_rows: Sequence[str] | None
) -> tuple[pd.DataFrame | None, str | None]:
    """Parse markdown table from LLM response into structured DataFrame.

    Validates table headers, row count, and cell structure.
    Normalizes HTML break tags to newlines.

    Args:
        markdown: Raw markdown string from LLM response.
        expected_rows: Optional sequence of expected row labels for validation.

    Returns:
        Tuple of (DataFrame, error_message).
        - On success: (DataFrame, None)
        - On failure: (None, error_message_string)
    """
    if not markdown:
        return None, "AI応答が空でした。"

    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    header_index = next(
        (idx for idx, line in enumerate(lines) if line.startswith("|")), None
    )
    if header_index is None:
        return None, "AI応答に表形式の結果が見つかりませんでした。"

    # Extract table lines
    table_lines: list[str] = []
    for line in lines[header_index:]:
        if not line.startswith("|"):
            break
        table_lines.append(line)

    if len(table_lines) < 2:
        return None, "AI応答の表が不完全です。"

    # Validate header
    header_cells = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    if tuple(header_cells) != EXPECTED_LLM_HEADERS:
        return None, "AI応答の表ヘッダーが期待と一致しません。"

    # Validate row count
    data_lines = table_lines[2:]  # Skip header and separator
    if expected_rows and len(data_lines) != len(expected_rows):
        return None, "AI応答の行数が想定と一致しません。"

    # Build iterator with optional row validation
    if expected_rows:
        iterator: Sequence[tuple[str | None, str]] = list(
            zip(expected_rows, data_lines, strict=True)
        )
    else:
        iterator = [(None, line) for line in data_lines]

    # Parse rows
    records: list[dict[str, str]] = []
    row_errors: list[str] = []
    for row_index, (expected_label, line) in enumerate(iterator, start=1):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(EXPECTED_LLM_HEADERS):
            if len(cells) < len(EXPECTED_LLM_HEADERS):
                missing = len(EXPECTED_LLM_HEADERS) - len(cells)
                original_count = len(cells)
                cells.extend([""] * missing)
                row_errors.append(
                    f"AI応答の列数が不足しています({row_index}行目: {original_count}/{len(EXPECTED_LLM_HEADERS)}列)"
                )
            else:
                extra = len(cells) - len(EXPECTED_LLM_HEADERS)
                cells = cells[: len(EXPECTED_LLM_HEADERS)]
                row_errors.append(
                    f"AI応答の列数が超過しています({row_index}行目: +{extra}列を切り捨て)"
                )
        if expected_label is not None and cells[0] != expected_label:
            return None, f"AI応答の項目順が想定と異なります({cells[0]})。"
        records.append(dict(zip(EXPECTED_LLM_HEADERS, cells, strict=True)))

    if not records:
        return None, "AI応答の行が見つかりませんでした。"

    # Create DataFrame and normalize break tags
    df = pd.DataFrame(records)
    for header in EXPECTED_LLM_HEADERS:
        if header in df.columns:
            df[header] = df[header].apply(
                lambda value: (
                    ""
                    if value is None
                    else str(value)
                    .strip()
                    .replace("<br />", "\n")
                    .replace("<br/>", "\n")
                    .replace("<br>", "\n")
                )
            )
    error_message = "\n".join(row_errors) if row_errors else None
    return df, error_message


def render_llm_results(
    session_manager: Any,
    actionable_changes: Sequence[Any],
    pfmea_context: Mapping[str, PfmeaContext | None],
) -> None:
    """Render AI inference results with PFMEA tables and download option.

    Displays results grouped by block, with styling to highlight AI-generated rows.
    Provides CSV download button for all aggregated results.

    Args:
        session_manager: Session manager providing LLM structured results.
        actionable_changes: Sequence of change objects to display results for.
        pfmea_context: Mapping from change_id to PFMEA context data.
    """
    if not actionable_changes:
        st.toast("変化点が無いためAI推定は実行されていません", icon=ICON_INFO)
        return

    structured_payload = session_manager.get_llm_structured_rows()
    rows_by_change: dict[str, list[dict[str, str]]] = structured_payload.get(
        "by_change", {}
    )
    if not rows_by_change:
        return

    aggregated_rows: list[dict[str, str]] = structured_payload.get("all_rows", [])

    eligible_changes = []
    missing_results = False

    # Filter changes with valid results
    for change in actionable_changes:
        change_id = getattr(change, "change_id", "")
        if not rows_by_change.get(change_id):
            missing_results = True
            continue
        eligible_changes.append(change)

    # Aggregate results by block
    tables_by_block = aggregate_pfmea_results(
        eligible_changes,
        pfmea_context,
        rows_by_change,
        block_order=PFMEA_BLOCKS,
    )
    tables_by_block = _filter_ai_only_tables(tables_by_block)

    if not tables_by_block:
        if missing_results:
            st.toast("AI推定結果はまだ生成されていません", icon=ICON_INFO)
        return

    # Display tables by block
    for block_label, table_df in tables_by_block.items():
        if table_df.empty:
            continue
        classification_series = table_df.get("区分")
        display_df = table_df.drop(columns=list(HIDDEN_COLUMNS), errors="ignore")
        st.caption(f"ブロック: {block_label}")
        html_table = style_pfmea_ai_dataframe(display_df, classification_series)
        st.markdown(html_table, unsafe_allow_html=True)

    # Provide download buttons
    if aggregated_rows:
        display_mapping_log_download_button()

        download_df = pd.DataFrame(aggregated_rows)
        download_df = download_df.drop(columns=list(HIDDEN_COLUMNS), errors="ignore")
        # Remove バリエーション column from output
        download_df = download_df.drop(columns=["バリエーション"], errors="ignore")
        ordered_columns = _build_download_columns(download_df.columns)
        if ordered_columns:
            download_df = download_df.reindex(columns=ordered_columns)
        download_df = download_df.fillna("")

        # UI表示と同様に参照列へAI接頭辞を付与
        download_df = download_df.rename(columns=AI_REFERENCE_COLUMN_ALIASES)

        # Get source variant for sheet name
        sheet_name = "AI推定結果"
        selection = session_manager.get_analysis_selection()
        if selection and len(selection) == 2:
            source_variant, _ = selection
            if source_variant:
                sheet_name = str(source_variant).strip()

        # Export to Excel format with styling
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            download_df.to_excel(writer, index=False, sheet_name=sheet_name)
            apply_excel_styling(writer.book[sheet_name])
        excel_bytes = buffer.getvalue()

        file_name = _build_assessment_filename(session_manager, aggregated_rows)
        st.download_button(
            label="AI推定結果をダウンロード",
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    _render_existing_pfmea_download(pfmea_context)


def render_llm_download_button(
    session_manager: SessionManager,
    *,
    key: str = "llm_download_header",
) -> bool:
    """AI推定結果のダウンロードボタンを表示する。

    Returns:
        True if download button was rendered, False otherwise.
    """
    from src.ui.state import SessionManager as SM

    llm_data = session_manager.get_llm_structured_rows()
    by_change = llm_data.get("by_change", {})
    if not by_change:
        return False

    # Aggregate rows from by_change
    aggregated_rows: list[dict[str, str]] = []
    for rows in by_change.values():
        if isinstance(rows, list):
            aggregated_rows.extend(rows)

    if not aggregated_rows:
        return False

    download_df = pd.DataFrame(aggregated_rows)
    download_df = download_df.drop(columns=list(HIDDEN_COLUMNS), errors="ignore")
    download_df = download_df.drop(columns=["バリエーション"], errors="ignore")
    ordered_columns = _build_download_columns(download_df.columns)
    if ordered_columns:
        download_df = download_df.reindex(columns=ordered_columns)
    download_df = download_df.fillna("")
    download_df = download_df.rename(columns=AI_REFERENCE_COLUMN_ALIASES)

    sheet_name = "AI推定結果"
    selection = session_manager.get_analysis_selection()
    if selection and len(selection) == 2:
        source_variant, _ = selection
        if source_variant:
            sheet_name = str(source_variant).strip()

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        download_df.to_excel(writer, index=False, sheet_name=sheet_name)
        apply_excel_styling(writer.book[sheet_name])
    excel_bytes = buffer.getvalue()

    file_name = _build_assessment_filename(session_manager, aggregated_rows)
    st.download_button(
        label="AI推定結果をダウンロード",
        data=excel_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key,
    )
    return True


def _filter_ai_only_tables(
    tables_by_block: Mapping[str, pd.DataFrame],
) -> OrderedDict[str, pd.DataFrame]:
    filtered: OrderedDict[str, pd.DataFrame] = OrderedDict()
    for block_label, table_df in tables_by_block.items():
        if table_df.empty or "区分" not in table_df.columns:
            continue
        ai_only = table_df[table_df["区分"] == PFMEA_AI_LABEL].copy()
        if not ai_only.empty:
            filtered[str(block_label)] = ai_only
    return filtered


def _build_existing_pfmea_download_df(
    pfmea_context: Mapping[str, PfmeaContext | None],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for context in pfmea_context.values():
        if context is None or context.data is None or context.data.empty:
            continue
        working = context.data.copy()
        block_series = None
        for candidate in ("block", "ブロック", "PFMEAブロック"):
            if candidate in working.columns:
                block_series = working.pop(candidate)
                break
        if block_series is None:
            fallback_block = context.block or "未分類ブロック"
            block_series = pd.Series(
                [fallback_block] * len(working),
                dtype=str,
            )
        else:
            fallback = context.block or "未分類ブロック"
            block_series = block_series.fillna(fallback)

        normalized = normalize_existing_pfmea(working)
        if normalized.empty:
            continue
        block_values = block_series.reset_index(drop=True).astype(str)
        normalized = normalized.reset_index(drop=True)
        normalized.insert(0, "ブロック", block_values)
        frames.append(normalized)

    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True).drop_duplicates()
    ordered_columns = ["ブロック", *PFMEA_COLUMN_ORDER]
    return result.reindex(columns=ordered_columns)


def _render_existing_pfmea_download(
    pfmea_context: Mapping[str, PfmeaContext | None],
) -> None:
    existing_df = _build_existing_pfmea_download_df(pfmea_context)
    if existing_df.empty:
        return

    sheet_name = "既存PFMEA"
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        existing_df.to_excel(writer, index=False, sheet_name=sheet_name)
        apply_excel_styling(writer.book[sheet_name])
    excel_bytes = buffer.getvalue()

    file_name = f"既存PFMEA_{datetime.now().strftime('%Y%m%d')}.xlsx"
    st.markdown(
        f"""
        <style>
        button[aria-label="↓"] {{
          padding: 2px 6px;
          font-size: {typography.SIZE_PX_12};
          line-height: 1;
          opacity: 0.25;
          color: {colors.TEXT_DISABLED};
          background: transparent;
          border: none;
        }}
        button[aria-label="↓"]:hover {{
          opacity: 0.6;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.download_button(
        label="↓",
        data=excel_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="existing_pfmea_download",
    )


def _build_download_columns(columns: Sequence[str]) -> list[str]:
    """Ensure Excel/CSV follows metadata + PFMEA 表示列の順序."""

    metadata_columns = [
        "ブロック",
        "ステーション",
        "対象部品",
        "変更種別",
    ]
    ordered: list[str] = []

    def _append(column: str) -> None:
        if column not in ordered:
            ordered.append(column)

    for column in metadata_columns:
        _append(column)

    for column in DISPLAY_COLUMNS:
        _append(column)

    for column in columns:
        _append(column)

    return ordered


def _build_assessment_filename(
    session_manager: Any, aggregated_rows: Sequence[Mapping[str, Any]]
) -> str:
    """ファイル名を変更後バリエーション名＋日付形式で組み立てる。"""

    variant_label = ""
    get_selection = getattr(session_manager, "get_analysis_selection", None)
    if callable(get_selection):
        selection = get_selection()
        if selection and len(selection) == 2:
            _, target_variant = selection
            variant_label = str(target_variant or "").strip()

    if not variant_label:
        for row in aggregated_rows:
            value = str(row.get("バリエーション", "") or "").strip()
            if value:
                variant_label = value
                break

    if not variant_label:
        variant_label = "pfmea"

    date_suffix = datetime.now().strftime("%Y%m%d")
    return f"{variant_label}アセス結果_{date_suffix}.xlsx"


__all__ = [
    "style_pfmea_ai_dataframe",
    "parse_llm_table",
    "render_llm_results",
    "PFMEA_TABLE_STYLES",
    "PFMEA_TABLE_STYLE_BLOCK",
]
