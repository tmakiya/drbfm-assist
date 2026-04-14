import re
import uuid
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from drassist.chains.drbfm_assist import (
    DrbfmAssistWorkflow,
    DrbfmAssistWorkflowState,
    DrbfmWorkflowContext,
)
from drassist.config.manager import ConfigManager

load_dotenv()


# --- Utility Functions (from 20250829_evaluate_workflow.py) ---


def format_reasoning_chains_as_markdown(reasoning_chains: List[str]) -> str:
    """Format reasoning chains as markdown bullet points"""
    if not reasoning_chains:
        return ""
    return "\n".join([f"- {reasoning}" for reasoning in reasoning_chains])


def decompose_project_number(project_number: str) -> tuple[str, str]:
    """Decompose project number into base and suffix"""
    pattern = re.compile(r"^(.*?)-(\d+)$")
    m = pattern.match(project_number)
    return (m.group(1), m.group(2)) if m else (project_number, "")


# --- Core Application Logic ---


@st.cache_resource
def get_workflow(product_segment: str = None):
    """Get and cache the compiled DRBFM assist workflow for a given product segment."""
    return DrbfmAssistWorkflow(
        config_path = "configs/70aaacd2.yaml", 
        gemini_model_name="gemini-2.5-pro", 
        product_segment=product_segment
    ).compile()


def run_drbfm_assist_workflow(
    raw_input: str,
    part: str,
    top_k: int,
    search_size: int,
    product_segment: str = None,
) -> Dict[str, Any]:
    """Run a single DRBFM assist workflow."""
    drbfm_assist_workflow = get_workflow(product_segment=product_segment)
    initial_state = DrbfmAssistWorkflowState(raw_input=raw_input, part=part)
    context = DrbfmWorkflowContext(top_k=top_k, search_size=search_size)

    try:
        result = drbfm_assist_workflow.invoke(initial_state, context=context)
        return result
    except Exception as e:
        st.error(f"ワークフローの実行中にエラーが発生しました: {e}")
        return {
            "change_points": [],
            "per_cp_results": [{"error": str(e)}],
            "error": str(e),
        }


def create_output_df(
    inputs: List[Dict[str, str]], results: List[Dict[str, Any]]
) -> pd.DataFrame:
    """Create a DataFrame from the workflow results."""
    output_rows = []
    for i, result in enumerate(results):
        input_data = inputs[i]
        per_cp_results = result.get("per_cp_results", [])

        if not per_cp_results:
            per_cp_results.append(
                {"error": "変更点が抽出されませんでした", "relevant_search_results": []}
            )

        for cp_result in per_cp_results:
            change_point = cp_result.get("change_point", "")
            search_results = cp_result.get("relevant_search_results", [])
            estimation_results = cp_result.get("estimation_results", {})
            error = cp_result.get("error", "")

            if not search_results:
                output_rows.append(
                    {
                        "項目": input_data["part"],
                        "変更": input_data["raw_input"],
                        "抽出された変更点": change_point,
                        "エラー詳細": error,
                    }
                )
            else:
                for search_result in search_results:
                    doc_id = search_result.get("doc_id", "")
                    estimation = estimation_results.get(doc_id, {})
                    if estimation:
                        estimation = estimation.model_dump()

                    project_number = search_result.get("project_number", "")
                    kanri_number, fugou = decompose_project_number(project_number)

                    output_rows.append(
                        {
                            "項目": input_data["part"],
                            "変更": input_data["raw_input"],
                            "抽出された変更点": change_point,
                            "機能": search_result.get("function", ""),
                            "推定不具合_内容": estimation.get("potential_defect", ""),
                            "推定不具合_原因": estimation.get("potential_cause", ""),
                            "推定不具合_対策": estimation.get("countermeasure", ""),
                            "推定不具合_根拠": format_reasoning_chains_as_markdown(
                                estimation.get("reasoning_chains", [])
                            ),
                            "検索結果_型式": search_result.get("model_number", ""),
                            "検索結果_ユニット(cause_unit)": search_result.get("cause", {}).get("unit", ""),
                            "検索結果_部位(cause_part)": search_result.get("cause", {}).get("part", ""),
                            "検索結果_変更(unit_part_change)": search_result.get("cause", {}).get("part_change", ""),
                            "検索結果_故障モード(failure_mode)": search_result.get("failure", {}).get("mode", ""),
                            "検索結果_故障影響(failure_effect)": search_result.get("failure", {}).get("effect", ""),
                            "参照ファイル名": search_result.get("project_number", ""),
                            "表題": search_result.get("title", ""),
                            "内容": search_result.get("content", ""),
                            "原因": search_result.get("cause", {}).get("original", ""),
                            "対策": search_result.get("countermeasure", ""),
                            "再発防止": search_result.get("recurrence_prevention", ""),
                            "エラー詳細": error,
                        }
                    )
    return pd.DataFrame(output_rows)


# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.title("AIリスク・対策抽出 for Kitz")

# --- Sidebar for parameters ---
with st.sidebar:
    st.header("パラメータ設定")

    # Load product segments from config
    config_manager = ConfigManager("configs/70aaacd2.yaml")
    model_numbers_config = config_manager.get("model_numbers", {})
    product_segments = ["すべて"] + list(model_numbers_config.keys())

    product_segment = st.selectbox("製品セグメント", options=product_segments)

    top_k = st.number_input("Top-K", min_value=1, max_value=50, value=5)
    search_size = st.number_input("Search Size", min_value=1, max_value=100, value=20)

# --- Main content ---
st.info("変更点を入力し、分析を実行してください。")

# Initialize session state for dynamic form
if "change_items" not in st.session_state:
    st.session_state.change_items = [{"id": str(uuid.uuid4()), "part": "", "raw_input": ""}]

# --- Input Tabs ---
tab1, tab2 = st.tabs(["フォーム入力", "CSVアップロード"])

inputs_to_process = []

with tab1:
    st.header("フォーム入力")
    for i, item in enumerate(st.session_state.change_items):
        with st.container():
            col1, col2, col3 = st.columns([4, 5, 1])
            st.session_state.change_items[i]["part"] = col1.text_input(
                "部品名", value=item["part"], key=f"part_{item['id']}"
            )
            st.session_state.change_items[i]["raw_input"] = col2.text_area(
                "変更点/変化点", value=item["raw_input"], key=f"raw_input_{item['id']}"
            )
            if i > 0:
                if col3.button("削除", key=f"delete_{item['id']}"):
                    st.session_state.change_items.pop(i)
                    st.rerun()

    if st.button("変更点/変化点を追加"):
        st.session_state.change_items.append({"id": str(uuid.uuid4()), "part": "", "raw_input": ""})
        st.rerun()

with tab2:
    st.header("CSVアップロード")
    uploaded_file = st.file_uploader(
        "ヘッダーが '項目' と '変更' のCSVファイルをアップロードしてください。", type="csv"
    )
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.dataframe(df)
            if "項目" in df.columns and "変更" in df.columns:
                st.success("CSVファイルを読み込みました。")
                inputs_to_process = [
                    {"part": row["項目"], "raw_input": row["変更"]}
                    for _, row in df.iterrows()
                ]
            else:
                st.error("CSVには '項目' と '変更' のカラムが必要です。")
        except Exception as e:
            st.error(f"CSVファイルの読み込み中にエラーが発生しました: {e}")

# --- Execution Button ---
if st.button("実行", type="primary"):
    if not inputs_to_process:  # If CSV not used, get from form
        inputs_to_process = [
            item for item in st.session_state.change_items if item["part"] and item["raw_input"]
        ]

    if not inputs_to_process:
        st.warning("処理する変更点がありません。フォームに入力するか、CSVをアップロードしてください。")
    else:
        # Use None if 'すべて' is selected
        selected_segment = product_segment if product_segment != "すべて" else None

        with st.spinner("ワークフローを実行中..."):
            results = []
            progress_bar = st.progress(0)
            for i, item in enumerate(inputs_to_process):
                result = run_drbfm_assist_workflow(
                    raw_input=item["raw_input"],
                    part=item["part"],
                    top_k=top_k,
                    search_size=search_size,
                    product_segment=selected_segment,
                )
                results.append(result)
                progress_bar.progress((i + 1) / len(inputs_to_process))

        st.session_state.results = results
        st.session_state.inputs = inputs_to_process
        st.success("ワークフローの実行が完了しました。")

# --- Output Display ---
if "results" in st.session_state:
    st.header("実行結果")

    output_df = create_output_df(st.session_state.inputs, st.session_state.results)

    # Display results in UI
    for i, input_data in enumerate(st.session_state.inputs):
        with st.expander(f"変更点 {i+1}: {input_data['part']} - {input_data['raw_input'][:50]}"):
            st.dataframe(output_df[(output_df["項目"] == input_data["part"]) & (output_df["変更"] == input_data["raw_input"])])

    # CSV Download
    csv_data = output_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="結果をCSVでダウンロード",
        data=csv_data,
        file_name="drbfm_assist_results.csv",
        mime="text/csv",
    )