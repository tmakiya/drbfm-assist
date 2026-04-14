"""DRBFM Purpose Workflow GUI Application

This application provides a GUI interface for executing DRBFM Purpose workflows.
Users can paste Excel data (TSV format) with "部品" and "変更点（変更内容・目的）" columns,
and the app will generate failure modes, causes, effects, and countermeasures.
"""

import io
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from loguru import logger
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from drassist.chains.drbfm_purpose_workflow import (
    DrbfmPurposeWorkflow,
    DrbfmPurposeWorkflowState,
    GeneratedFailureMode,
)

load_dotenv()

# Configure logger
logger.add("logs/app_drbfm_purpose_{time}.log", rotation="1 day", retention="7 days")


# --- Constants ---
PART_COLUMN = "部品"
CHANGE_POINT_COLUMN = "変更点（変更内容・目的）"

# Excel output column names
EXCEL_COLUMNS = [
    "No",
    "部品",
    "遵守規定（JIS,JIA,確認シート）",
    "変更点（変更内容・目的）",
    "機能",
    "変更がもたらす機能の損失、商品性の欠如",
    "他の心配点はないか（DRBFM）",
    "原因・要因",
    "他にかんがえるべき要因はないか（DRBFM）",
    "お客様への影響",
    "重要度",
    "心配点を取り除くためにどんな設計をしたか(設計遵守事項、チェックシート等)",
    "予測理由",
    "ソース種別",
    "ソースURL",
    "ソースの対象部位",
    "ソースの部品",
    "ソースの機能分類",
    "ソースの機能",
    "ソースの変更点",
    "ソースの故障モード",
    "ソースの原因・要因",
    "ソースのお客様への影響",
    "ソースの対策",
]


# --- Utility Functions ---


def parse_tsv_input(text: str) -> Tuple[pd.DataFrame, str]:
    """Parse TSV text (copied from Excel) into a DataFrame.
    
    Returns:
        Tuple of (DataFrame, error_message). If successful, error_message is empty.
    """
    if not text.strip():
        return pd.DataFrame(), "入力が空です。"
    
    try:
        # Try to parse as TSV (tab-separated)
        df = pd.read_csv(io.StringIO(text), sep="\t")
        
        # Check for required columns
        if PART_COLUMN not in df.columns:
            return pd.DataFrame(), f"「{PART_COLUMN}」列が見つかりません。"
        if CHANGE_POINT_COLUMN not in df.columns:
            return pd.DataFrame(), f"「{CHANGE_POINT_COLUMN}」列が見つかりません。"
        
        # Filter to only required columns and remove empty rows
        df = df[[PART_COLUMN, CHANGE_POINT_COLUMN]].dropna(how="all")
        df = df[df[PART_COLUMN].notna() & df[CHANGE_POINT_COLUMN].notna()]
        
        if df.empty:
            return pd.DataFrame(), "有効なデータ行がありません。"
        
        return df, ""
    
    except Exception as e:
        return pd.DataFrame(), f"パースエラー: {str(e)}"


def format_list_field(values: List[str]) -> str:
    """Format a list of values as a single text field."""
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "[" + ", ".join(f"{{{v}}}" for v in values) + "]"


def process_single_input(
    workflow: DrbfmPurposeWorkflow,
    part: str,
    change_point: str,
    index: int,
) -> Dict[str, Any]:
    """Process a single (part, change_point) pair through the workflow."""
    logger.info(f"Processing input {index}: part='{part[:30]}...', change_point='{change_point[:30]}...'")
    
    try:
        initial_state = DrbfmPurposeWorkflowState(
            part=part,
            change_point=change_point,
        )
        
        result = workflow.invoke(
            initial_state,
            config={"run_name": f"DRBFM Purpose - {index}"}
        )
        
        return {
            "index": index,
            "part": part,
            "change_point": change_point,
            "input_function_category": result.get("input_function_category", ""),
            "generated_failure_modes": result.get("generated_failure_modes", []),
            "error": None,
        }
    
    except Exception as e:
        logger.error(f"Error processing input {index}: {e}")
        return {
            "index": index,
            "part": part,
            "change_point": change_point,
            "input_function_category": "",
            "generated_failure_modes": [],
            "error": str(e),
        }


def aggregate_results(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """Aggregate workflow results into a DataFrame for Excel export.
    
    Groups by (部品, 変更点, 機能, failure_mode, cause, effect, countermeasure)
    and aggregates source fields into list format.
    """
    rows = []
    
    for result in results:
        part = result["part"]
        change_point = result["change_point"]
        input_function_category = result["input_function_category"]
        failure_modes = result["generated_failure_modes"]
        
        if not failure_modes:
            # No results - create empty row
            rows.append({
                "部品": part,
                "変更点（変更内容・目的）": change_point,
                "機能": input_function_category,
                "変更がもたらす機能の損失、商品性の欠如": "",
                "原因・要因": "",
                "お客様への影響": "",
                "心配点を取り除くためにどんな設計をしたか(設計遵守事項、チェックシート等)": "",
                "予測理由": "",
                "ソース種別": "",
                "ソースURL": "",
                "ソースの対象部位": "",
                "ソースの部品": "",
                "ソースの機能分類": "",
                "ソースの機能": "",
                "ソースの変更点": "",
                "ソースの故障モード": "",
                "ソースの原因・要因": "",
                "ソースのお客様への影響": "",
                "ソースの対策": "",
            })
            continue
        
        # Group by unique combination
        grouped = {}
        for fm in failure_modes:
            key = (
                part,
                change_point,
                input_function_category,
                fm.failure_mode,
                fm.cause,
                fm.effect,
                fm.countermeasure,
            )
            
            if key not in grouped:
                grouped[key] = {
                    "reasoning": [],
                    "source_type": [],
                    "source_URL": [],
                    "source_section": [],
                    "source_part": [],
                    "source_function_category": [],
                    "source_function": [],
                    "source_change_point": [],
                    "source_failure_mode": [],
                    "source_cause": [],
                    "source_effect": [],
                    "source_countermeasure": [],
                }
            
            # Add reasoning
            if fm.reasoning:
                grouped[key]["reasoning"].append(fm.reasoning)
            
            # Add reference fields
            for ref in fm.references:
                grouped[key]["source_type"].append(ref.source_type)
                grouped[key]["source_URL"].append(ref.source_URL)
                grouped[key]["source_section"].append(ref.source_section)
                grouped[key]["source_part"].append(ref.source_part)
                grouped[key]["source_function_category"].append(ref.source_function_category)
                grouped[key]["source_function"].append(ref.source_function)
                grouped[key]["source_change_point"].append(ref.source_change_point)
                grouped[key]["source_failure_mode"].append(ref.source_failure_mode)
                grouped[key]["source_cause"].append(ref.source_cause)
                grouped[key]["source_effect"].append(ref.source_effect)
                grouped[key]["source_countermeasure"].append(ref.source_countermeasure)
        
        # Create rows from grouped data
        for key, sources in grouped.items():
            rows.append({
                "部品": key[0],
                "変更点（変更内容・目的）": key[1],
                "機能": key[2],
                "変更がもたらす機能の損失、商品性の欠如": key[3],
                "原因・要因": key[4],
                "お客様への影響": key[5],
                "心配点を取り除くためにどんな設計をしたか(設計遵守事項、チェックシート等)": key[6],
                "予測理由": format_list_field(sources["reasoning"]),
                "ソース種別": format_list_field(sources["source_type"]),
                "ソースURL": format_list_field(sources["source_URL"]),
                "ソースの対象部位": format_list_field(sources["source_section"]),
                "ソースの部品": format_list_field(sources["source_part"]),
                "ソースの機能分類": format_list_field(sources["source_function_category"]),
                "ソースの機能": format_list_field(sources["source_function"]),
                "ソースの変更点": format_list_field(sources["source_change_point"]),
                "ソースの故障モード": format_list_field(sources["source_failure_mode"]),
                "ソースの原因・要因": format_list_field(sources["source_cause"]),
                "ソースのお客様への影響": format_list_field(sources["source_effect"]),
                "ソースの対策": format_list_field(sources["source_countermeasure"]),
            })
    
    # Create DataFrame with all columns
    df = pd.DataFrame(rows)
    
    # Add empty columns
    df["No"] = ""
    df["遵守規定（JIS,JIA,確認シート）"] = ""
    df["他の心配点はないか（DRBFM）"] = ""
    df["他にかんがえるべき要因はないか（DRBFM）"] = ""
    df["重要度"] = ""
    
    # Reorder columns
    df = df[EXCEL_COLUMNS]
    
    return df


def create_excel_file(df: pd.DataFrame) -> bytes:
    """Create an Excel file from a DataFrame."""
    wb = Workbook()
    ws = wb.active
    ws.title = "DRBFM Draft"
    
    # Write data
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=value)
    
    # Adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


# --- Streamlit UI ---


def main():
    st.set_page_config(
        page_title="DRBFM Assist Agent for PURPOSE",
        page_icon="📋",
        layout="wide"
    )
    
    st.title("📋 DRBFM Assist Agent for PURPOSE")
    st.caption("過去のDRBFM記録と不具合報告から故障モードをドラフトします")
    
    # --- Sidebar ---
    with st.sidebar:
        st.header("⚙️ 設定")
        st.markdown("---")
        
        max_workers = st.number_input(
            "並列処理数",
            min_value=1,
            max_value=8,
            value=4,
            help="同時に処理する入力の数"
        )
        
        st.markdown("---")
        st.info(
            "**使用方法**\n"
            "1. Excelから「部品」と「変更点（変更内容・目的）」を含む表をコピー\n"
            "2. テキストエリアにペースト\n"
            "3. 「実行」ボタンをクリック\n"
            "4. 結果をExcelでダウンロード"
        )
    
    # --- Main Content ---
    st.markdown("### 📝 入力")
    st.info(
        "Excelから表をコピー＆ペーストしてください。\n"
        "ヘッダーに「部品」と「変更点（変更内容・目的）」が含まれている必要があります。"
    )
    
    # Text area for paste input
    input_text = st.text_area(
        "Excelからコピーした表をここにペースト",
        height=200,
        placeholder="部品\t変更点（変更内容・目的）\nケース\tサイズを小型化する\n...",
    )
    
    # Parse and preview
    if input_text:
        df_input, error = parse_tsv_input(input_text)
        
        if error:
            st.error(f"❌ {error}")
        else:
            st.success(f"✅ {len(df_input)}件の入力を検出しました")
            
            with st.expander("入力プレビュー", expanded=True):
                st.dataframe(df_input, use_container_width=True, hide_index=True)
    
    # --- Execution ---
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        execute_button = st.button("🚀 実行", type="primary")
    
    # Initialize session state
    if "results" not in st.session_state:
        st.session_state.results = None
    if "output_df" not in st.session_state:
        st.session_state.output_df = None
    
    if execute_button:
        if not input_text:
            st.warning("⚠️ 入力がありません。")
        else:
            df_input, error = parse_tsv_input(input_text)
            
            if error:
                st.error(f"❌ {error}")
            else:
                st.markdown("### 🔄 処理中...")
                
                # Initialize workflow
                with st.spinner("ワークフローを初期化中..."):
                    workflow = DrbfmPurposeWorkflow()
                
                # Process inputs in parallel
                inputs = [
                    (row[PART_COLUMN], row[CHANGE_POINT_COLUMN])
                    for _, row in df_input.iterrows()
                ]
                
                total = len(inputs)
                completed = 0
                
                # Show progress bar from the start (0%)
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.text(f"処理中: {completed}/{total} 件完了")
                
                results = []
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    for i, (part, change_point) in enumerate(inputs):
                        future = executor.submit(
                            process_single_input,
                            workflow,
                            part,
                            change_point,
                            i,
                        )
                        futures[future] = i
                    
                    for future in as_completed(futures):
                        result = future.result()
                        results.append(result)
                        completed += 1
                        
                        progress_bar.progress(completed / total)
                        status_text.text(f"処理中: {completed}/{total} 件完了")
                
                # Sort results by original index
                results.sort(key=lambda x: x["index"])
                
                status_text.text("完了！")
                st.success(f"✅ {total}件の処理が完了しました")
                st.balloons()
                
                # Aggregate results
                output_df = aggregate_results(results)
                
                # Store in session state
                st.session_state.results = results
                st.session_state.output_df = output_df
    
    # --- Output Display ---
    if st.session_state.output_df is not None:
        st.markdown("---")
        st.markdown("### 📊 結果")
        
        output_df = st.session_state.output_df
        
        st.info(f"出力行数: {len(output_df)}件")
        
        # Display results
        st.dataframe(output_df, use_container_width=True, hide_index=True)
        
        # Download button
        st.markdown("---")
        st.markdown("### 💾 ダウンロード")
        
        excel_data = create_excel_file(output_df)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        st.download_button(
            label="📥 Excelファイルをダウンロード",
            data=excel_data,
            file_name=f"drbfm_draft_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        
        # Summary
        st.markdown("---")
        st.markdown("### 📈 サマリー")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            unique_inputs = output_df[["部品", "変更点（変更内容・目的）"]].drop_duplicates()
            st.metric("入力件数", len(unique_inputs))
        
        with col2:
            st.metric("出力行数", len(output_df))
        
        with col3:
            unique_failure_modes = output_df["変更がもたらす機能の損失、商品性の欠如"].nunique()
            st.metric("故障モード種類", unique_failure_modes)


if __name__ == "__main__":
    main()
