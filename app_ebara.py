"""
DRBFM Workflow Application for Ebara Corporation (荏原製作所)
This application provides a GUI interface for executing DRBFM workflows with direct change point input.
"""

import uuid
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from loguru import logger

from drassist.chains.drbfm_workflow_8d8232f3 import DrbfmWorkflow, DrbfmWorkflowState

load_dotenv()

# Configure logger
logger.add("logs/app_ebara_{time}.log", rotation="1 day", retention="7 days")


# --- Utility Functions ---

def format_reasoning_chains_as_markdown(reasoning_chains: List[str]) -> str:
    """Format reasoning chains as markdown bullet points"""
    if not reasoning_chains:
        return ""
    return "\n".join([f"- {reasoning}" for reasoning in reasoning_chains])


def format_search_history_as_markdown(search_history: List[Dict[str, Any]]) -> str:
    """Format search history as markdown bullet points"""
    if not search_history:
        return ""
    
    lines = []
    for entry in search_history:
        stage = entry.get("stage", "")
        method = entry.get("method", "")
        doc_ids = entry.get("doc_ids", [])
        
        line = f"- Stage {stage}: {method}"
        if doc_ids:
            line += f" - doc_ids: {', '.join([str(i) for i in doc_ids])}"
        lines.append(line)
    
    return "\n".join(lines)


# --- Core Application Logic ---

@st.cache_resource
def get_workflow():
    """Get and cache the compiled DRBFM workflow."""
    try:
        workflow = DrbfmWorkflow(
            config_path="configs/8d8232f3.yaml",
            gemini_model_name="gemini-2.5-pro"
        )
        logger.info("DRBFM Workflow initialized successfully")
        return workflow
    except Exception as e:
        logger.error(f"Failed to initialize workflow: {e}")
        st.error(f"ワークフローの初期化に失敗しました: {e}")
        return None


def run_drbfm_workflow(
    change: str,
    top_k: int = 5,
    search_size: int = 10,
    thread_id: int = 1
) -> Dict[str, Any]:
    """Run a single DRBFM workflow with the given change point."""
    
    # Format change point
    change_point = change
    
    # Get workflow instance
    drbfm_workflow = get_workflow()
    if not drbfm_workflow:
        return {"error": "ワークフローの初期化に失敗しました"}
    
    # Create initial state
    initial_state = DrbfmWorkflowState(
        change_point=change_point,
        top_k=top_k,
        search_size=search_size
    )
    
    logger.info(f"Starting DRBFM workflow for change point: {change_point[:100]}...")
    
    try:
        # Run workflow
        config = {
            "configurable": {"thread_id": thread_id},
            "run_name": "DRBFM Workflow Ebara",
        }
        
        result = drbfm_workflow.invoke(
            initial_state=initial_state,
            config=config
        )
        
        logger.info(f"Workflow completed successfully for: {change_point[:100]}...")
        return result
        
    except Exception as e:
        error_msg = f"ワークフロー実行エラー: {str(e)}"
        logger.error(f"DRBFM workflow failed for change point: {change_point[:100]}... Error: {error_msg}")
        return {
            "relevant_search_results": [],
            "estimation_results": {},
            "query_attributes": None,
            "search_history": [],
            "error": error_msg
        }


def create_output_rows(
    change: str,
    result: Dict[str, Any],
    row_id: int
) -> List[Dict[str, Any]]:
    """Create output rows from workflow results."""
    output_rows = []
    
    # Extract workflow results
    search_results = result.get("relevant_search_results", [])
    estimation_results = result.get("estimation_results", {})
    query_attributes = result.get("query_attributes", None)
    error = result.get("error")
    
    if error:
        logger.warning(f"Error detected in workflow result: {error}")
    
    # If no search results, create one row with empty search result fields
    if not search_results:
        output_row = {
            "ID": row_id,
            "変更": change,
            "推定不具合_内容": "",
            "推定不具合_原因": "",
            "推定不具合_対策": "",
            "推定不具合_根拠": "",
            "DrawerURL": "",
            "検索結果_ユニット": "",
            "検索結果_部位": "",
            "検索結果_変更": "",
            "検索結果_故障モード": "",
            "検索結果_故障影響": "",
            "検索結果_対策": "",
        }
        output_rows.append(output_row)
    else:
        # Create one row per search result
        for result_item in search_results:
            doc_id = result_item.get("doc_id", "")
            
            # Get estimation result
            estimation_data = {}
            if doc_id in estimation_results:
                estimation_result = estimation_results[doc_id]
                if hasattr(estimation_result, "model_dump"):
                    estimation_data = estimation_result.model_dump()
                else:
                    estimation_data = estimation_result
            
            # Generate DrawerURL
            original_id = result_item.get("original_id", "")
            drawer_url = f"https://caddi-drawer.com/8d8232f3-010d-4857-bf20-0cc7dc42ad97/documents/{original_id}" if original_id else ""
            
            output_row = {
                "ID": row_id,
                "変更": change,
                "推定不具合_内容": estimation_data.get("potential_defect", ""),
                "推定不具合_原因": estimation_data.get("potential_cause", ""),
                "推定不具合_対策": estimation_data.get("countermeasure", ""),
                "推定不具合_根拠": format_reasoning_chains_as_markdown(
                    estimation_data.get("reasoning_chains", [])
                ),
                "DrawerURL": drawer_url,
                "検索結果_ユニット": result_item.get("cause", {}).get("unit", ""),
                "検索結果_部位": result_item.get("cause", {}).get("part", ""),
                "検索結果_変更": result_item.get("cause", {}).get("part_change", ""),
                "検索結果_故障モード": result_item.get("failure", {}).get("mode", ""),
                "検索結果_故障影響": result_item.get("failure", {}).get("effect", ""),
                "検索結果_対策": result_item.get("countermeasures", ""),
            }
            output_rows.append(output_row)
    
    return output_rows


def create_output_dataframe(
    inputs: List[Dict[str, str]],
    results: List[Dict[str, Any]]
) -> pd.DataFrame:
    """Create a complete output DataFrame from all workflow results."""
    all_output_rows = []
    
    for i, (input_data, result) in enumerate(zip(inputs, results)):
        output_rows = create_output_rows(
            change=input_data["change"],
            result=result,
            row_id=i + 1
        )
        all_output_rows.extend(output_rows)
    
    return pd.DataFrame(all_output_rows)


# --- Streamlit UI ---

def main():
    st.set_page_config(
        page_title="DRBFM Workflow - 荏原製作所",
        page_icon="🔧",
        layout="wide"
    )
    
    st.title("DRBFM Workflow Application")
    st.caption("荏原製作所向けDRBFMワークフロー実行システム")
    
    # --- Sidebar for parameters ---
    with st.sidebar:
        st.header("⚙️ パラメータ設定")
        st.markdown("---")
        
        top_k = st.number_input(
            "Top-K",
            min_value=1,
            max_value=50,
            value=5,
            help="各変更点に対して保持する検索結果の上位件数"
        )
        
        search_size = st.number_input(
            "Search Size",
            min_value=1,
            max_value=100,
            value=10,
            help="各検索で取得する結果の件数"
        )
        
        st.markdown("---")
        st.info(
            "**使用方法**\n"
            "1. フォーム入力またはCSVアップロードで変更点を入力\n"
            "2. パラメータを調整（必要に応じて）\n"
            "3. 実行ボタンをクリック\n"
            "4. 結果を確認・ダウンロード"
        )
    
    # --- Main content ---
    st.markdown("### 📝 変更点入力")
    st.info("「変更」を入力してDRBFMワークフローを実行します。")
    
    # Initialize session state for dynamic form
    if "change_items" not in st.session_state:
        st.session_state.change_items = [
            {"id": str(uuid.uuid4()), "change": ""}
        ]
    
    if "results" not in st.session_state:
        st.session_state.results = None
    
    if "inputs" not in st.session_state:
        st.session_state.inputs = None
    
    # --- Input Tabs ---
    tab1, tab2 = st.tabs(["📋 フォーム入力", "📁 CSVアップロード"])
    
    inputs_to_process = []
    
    with tab1:
        st.markdown("#### フォームによる入力")
        st.caption("複数の変更点を入力できます。「変更点を追加」ボタンで入力欄を増やせます。")
        
        for i, item in enumerate(st.session_state.change_items):
            with st.container():
                col1, col2 = st.columns([8, 1])
                
                with col1:
                    st.session_state.change_items[i]["change"] = st.text_area(
                        "変更",
                        value=item["change"],
                        key=f"change_{item['id']}",
                        placeholder="例: 材質をSUS304からSUS316に変更",
                        height=80
                    )
                
                with col2:
                    st.markdown("")  # Spacing
                    st.markdown("")  # Spacing
                    if i > 0:  # Don't show delete button for first item
                        if st.button("🗑️", key=f"delete_{item['id']}", help="この入力を削除"):
                            st.session_state.change_items.pop(i)
                            st.rerun()
        
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            if st.button("➕ 変更点を追加", type="secondary"):
                st.session_state.change_items.append({
                    "id": str(uuid.uuid4()),
                    "change": ""
                })
                st.rerun()
    
    with tab2:
        st.markdown("#### CSVファイルによる入力")
        st.caption("ヘッダーが「変更」のCSVファイルをアップロードしてください。")
        
        uploaded_file = st.file_uploader(
            "CSVファイルを選択",
            type=["csv"],
            help="CSVファイルには「変更」の列が必要です"
        )
        
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                
                # Check for required columns
                if "変更" in df.columns:
                    st.success(f"✅ CSVファイルを読み込みました（{len(df)}件の変更点）")
                    
                    # Preview the data
                    with st.expander("データプレビュー", expanded=True):
                        st.dataframe(df[["変更"]].head(10))
                    
                    # Convert to input format
                    inputs_to_process = [
                        {"change": str(row["変更"])}
                        for _, row in df.iterrows()
                        if pd.notna(row["変更"])
                    ]
                else:
                    st.error("❌ CSVファイルには「変更」の列が必要です。")
                    st.caption("現在の列: " + ", ".join(df.columns))
                    
            except Exception as e:
                st.error(f"❌ CSVファイルの読み込みに失敗しました: {e}")
    
    # --- Execution Section ---
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        execute_button = st.button("🚀 実行", type="primary", disabled=False)
    
    if execute_button:
        # Get inputs from form if CSV not used
        if not inputs_to_process:
            inputs_to_process = [
                {"change": item["change"]}
                for item in st.session_state.change_items
                if item["change"].strip()
            ]
        
        if not inputs_to_process:
            st.warning("⚠️ 処理する変更点がありません。フォームに入力するか、CSVをアップロードしてください。")
        else:
            st.markdown("### 🔄 処理中...")
            
            # Process each change point
            results = []
            progress_container = st.container()
            
            with progress_container:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, item in enumerate(inputs_to_process):
                    status_text.text(f"処理中: {i+1}/{len(inputs_to_process)} - {item['change'][:50]}...")
                    
                    result = run_drbfm_workflow(
                        change=item["change"],
                        top_k=top_k,
                        search_size=search_size,
                        thread_id=i
                    )
                    results.append(result)
                    
                    progress_bar.progress((i + 1) / len(inputs_to_process))
                
                status_text.text("完了！")
            
            # Store results in session state
            st.session_state.results = results
            st.session_state.inputs = inputs_to_process
            
            st.success(f"✅ ワークフローの実行が完了しました（{len(inputs_to_process)}件の変更点を処理）")
            st.balloons()
    
    # --- Output Display ---
    if st.session_state.results and st.session_state.inputs:
        st.markdown("---")
        st.markdown("### 📊 実行結果")
        
        # Create output DataFrame
        output_df = create_output_dataframe(
            st.session_state.inputs,
            st.session_state.results
        )
        
        # Display results tabs
        result_tab1, result_tab2 = st.tabs(["📋 変更点別表示", "📊 全体表示"])
        
        with result_tab1:
            st.markdown("#### 変更点ごとの結果")
            
            for i, input_data in enumerate(st.session_state.inputs):
                with st.expander(
                    f"🔍 変更点 {i+1}: {input_data['change'][:50]}...",
                    expanded=(i == 0)  # Expand first item by default
                ):
                    # Filter DataFrame for this specific change point
                    filtered_df = output_df[
                        (output_df["変更"] == input_data["change"])
                    ]
                    
                    if not filtered_df.empty:
                        # Show summary
                        st.info(f"検索結果: {len(filtered_df)}件")
                        
                        # Display the data
                        st.dataframe(
                            filtered_df,
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.warning("該当する結果がありません。")
        
        with result_tab2:
            st.markdown("#### 全結果一覧")
            st.info(f"総結果数: {len(output_df)}件")
            
            # Display full DataFrame
            st.dataframe(
                output_df,
                use_container_width=True,
                hide_index=True
            )
        
        # --- CSV Download Section ---
        st.markdown("---")
        st.markdown("### 💾 結果のダウンロード")
        
        # Prepare CSV data
        csv_data = output_df.to_csv(index=False).encode('utf-8-sig')  # UTF-8 with BOM for Excel
        
        st.download_button(
            label="📥 結果をダウンロード",
            data=csv_data,
            file_name="drbfm_results_ebara.csv",
            mime="text/csv",
            type="primary"
        )
        
        # Summary statistics
        st.markdown("---")
        st.markdown("### 📈 サマリー")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("処理した変更点", len(st.session_state.inputs))
        
        with col2:
            st.metric("総検索結果", len(output_df))
        
        with col3:
            # Count unique defects
            unique_defects = output_df["推定不具合_内容"].dropna().nunique()
            st.metric("推定不具合種類", unique_defects)
        
        with col4:
            # Count results with countermeasures
            with_countermeasures = len(output_df[output_df["推定不具合_対策"].notna()])
            st.metric("対策提案あり", with_countermeasures)


if __name__ == "__main__":
    main()
