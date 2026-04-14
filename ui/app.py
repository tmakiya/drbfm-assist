"""DRBFM Workflow Application for Ebara Corporation (荏原製作所)
This application provides a GUI interface for executing DRBFM workflows with direct change point input.
"""

import asyncio
import uuid

import pandas as pd
import streamlit as st

from src import (
    create_output_dataframe,
    fetch_execution_history,
    load_batch_results,
    load_thread_results,
    run_drbfm_workflows_batch,
)
from src.csv_utils import parse_csv
from src.validators import validate_change_points


def render_input_form():
    """Render the input form for new workflow execution."""
    # --- Search Parameters ---
    with st.expander("検索パラメータ", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            top_k = st.slider(
                "Top-K（上位結果数）",
                min_value=1,
                max_value=50,
                value=5,
                help="各変更点に対して保持する検索結果の上位件数",
            )
        with col2:
            search_size = st.slider(
                "Search Size（検索件数）",
                min_value=1,
                max_value=100,
                value=10,
                help="各検索で取得する結果の件数",
            )

    # --- Input Tabs ---
    st.subheader("変更点入力")

    tab1, tab2 = st.tabs(["フォーム入力", "CSVアップロード"])

    inputs_to_process = []
    execute_button = False

    with tab1:
        st.info("複数の変更点を入力できます。「変更点を追加」ボタンで入力欄を増やせます")

        for i, item in enumerate(st.session_state.change_items):
            with st.container(border=True):
                col_header1, col_header2 = st.columns([5, 1])
                with col_header1:
                    st.markdown(f"**変更点 #{i + 1}**")
                with col_header2:
                    if i > 0:  # Don't show delete button for first item
                        if st.button("削除", key=f"delete_{item['id']}", type="secondary", width="stretch"):
                            st.session_state.change_items.pop(i)
                            st.rerun()

                st.session_state.change_items[i]["change"] = st.text_area(
                    "変更",
                    value=item["change"],
                    key=f"change_{item['id']}",
                    placeholder="例：材質をSUS304からSUS316に変更",
                    height=80,
                    label_visibility="visible",
                )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("+ 変更点を追加", type="secondary", width="stretch"):
                st.session_state.change_items.append({"id": str(uuid.uuid4()), "change": ""})
                st.rerun()
        with col2:
            if len(st.session_state.change_items) > 1:
                if st.button("変更点を全てクリア", type="secondary", width="stretch"):
                    st.session_state.change_items = [{"id": str(uuid.uuid4()), "change": ""}]
                    st.rerun()
        with col4:
            is_executing = st.session_state.get("is_executing", False)
            execute_button = st.button(
                "実行中..." if is_executing else "ワークフロー実行",
                key="execute_form",
                type="primary",
                width="stretch",
                disabled=is_executing,
            )

    with tab2:
        st.info("「変更」のヘッダーを含むCSVファイルをアップロードしてください")

        # CSV template download
        col1, col2 = st.columns([1, 3])
        with col1:
            template_df = pd.DataFrame(
                {
                    "変更": ["材質をSUS304からSUS316に変更", "回転数を1500rpmから1800rpmに増加"],
                }
            )
            csv_template = template_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="テンプレートをダウンロード",
                data=csv_template,
                file_name="drbfm_template.csv",
                mime="text/csv",
                width="stretch",
            )

        uploaded_file = st.file_uploader(
            "CSVファイルを選択", type=["csv"], help="CSVファイルには「変更」の列が必要です"
        )

        if uploaded_file:
            df, csv_warnings, csv_errors = parse_csv(uploaded_file)

            # エラーはst.error()のみで表示（toastは使わない）
            for error in csv_errors:
                st.error(error)

            # 警告はst.warning() + toastで表示
            for warning in csv_warnings:
                st.warning(warning)
                st.toast(warning, icon="⚠️")

            if df is not None:
                st.success(f"CSVファイルを読み込みました（{len(df)}件の変更点）")

                # Preview the data
                with st.expander("データプレビュー", expanded=True):
                    st.dataframe(df.head(10), width="stretch", hide_index=True)
                    if len(df) > 10:
                        st.caption(f"※ 上位10件を表示中（全{len(df)}件）")

                # Convert to input format
                inputs_to_process = [
                    {"change": str(row["変更"]).strip()} for _, row in df.iterrows()
                ]

                col1, col2, col3, col4 = st.columns(4)
                with col4:
                    is_executing = st.session_state.get("is_executing", False)
                    execute_button = st.button(
                        "実行中..." if is_executing else "ワークフロー実行",
                        key="execute_file",
                        type="primary",
                        width="stretch",
                        disabled=is_executing,
                    )

    return execute_button, inputs_to_process, top_k, search_size


def render_results():
    """Render the results display section."""
    if not st.session_state.results or not st.session_state.inputs:
        return

    # Create output DataFrame
    output_df = create_output_dataframe(st.session_state.inputs, st.session_state.results)

    # Count rows with actual search results (non-empty 検索結果_変更)
    total_search_count = len(
        output_df[output_df["検索結果_変更"].notna() & (output_df["検索結果_変更"] != "")]
    )

    st.subheader("実行結果")
    st.metric("総結果数", f"{total_search_count}件", delta=None)

    # Display results tabs
    result_tab1, result_tab2, result_tab3 = st.tabs(["変更点別表示", "全体表示", "統計情報"])

    with result_tab1:
        st.info("各変更点の詳細結果を確認できます")

        for i, input_data in enumerate(st.session_state.inputs):
            # Filter DataFrame for this specific change point
            filtered_df = output_df[output_df["変更"] == input_data["change"]]

            # Create expander title
            expander_title = (
                f"変更点 {i + 1}: "
                f"{input_data['change'][:50]}{'...' if len(input_data['change']) > 50 else ''}"
            )

            with st.expander(expander_title, expanded=(i == 0)):
                if not filtered_df.empty:
                    # Summary metrics (filter out empty strings as well as NaN)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        # Count rows that have actual search results (non-empty 検索結果_変更)
                        search_count = len(
                            filtered_df[
                                filtered_df["検索結果_変更"].notna() & (filtered_df["検索結果_変更"] != "")
                            ]
                        )
                        st.metric("検索結果", f"{search_count}件")
                    with col2:
                        # Filter out both NaN and empty strings before counting unique values
                        defect_series = filtered_df["推定不具合_内容"].dropna()
                        defect_series = defect_series[defect_series != ""]
                        unique_defects = defect_series.nunique()
                        st.metric("推定不具合種類", f"{unique_defects}種類")
                    with col3:
                        countermeasure_col = filtered_df["推定不具合_対策"]
                        with_countermeasures = len(
                            filtered_df[countermeasure_col.notna() & (countermeasure_col != "")]
                        )
                        st.metric("対策提案", f"{with_countermeasures}件")

                    # Display the data
                    st.dataframe(
                        filtered_df,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "DrawerURL": st.column_config.LinkColumn("DrawerURL", display_text="リンク")
                        },
                    )
                else:
                    st.warning("該当する結果がありません")

    with result_tab2:
        st.info(f"全{total_search_count}件の結果を一覧表示しています")

        # Display full DataFrame with better formatting
        st.dataframe(
            output_df,
            width="stretch",
            hide_index=True,
            column_config={"DrawerURL": st.column_config.LinkColumn("DrawerURL", display_text="リンク")},
        )

    with result_tab3:
        st.info("実行結果の統計情報を表示しています")

        # Summary statistics in columns (filter out empty strings as well as NaN)
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("処理した変更点", len(st.session_state.inputs), help="実行した変更点の総数")

        with col2:
            st.metric("総検索結果", total_search_count, help="全変更点の検索結果の総数")

        with col3:
            defect_series = output_df["推定不具合_内容"].dropna()
            defect_series = defect_series[defect_series != ""]
            unique_defects = defect_series.nunique()
            st.metric("推定不具合種類", unique_defects, help="ユニークな推定不具合の数")

        with col4:
            with_countermeasures = len(
                output_df[
                    output_df["推定不具合_対策"].notna() & (output_df["推定不具合_対策"] != "")
                ]
            )
            st.metric("対策提案あり", with_countermeasures, help="対策が提案された結果の数")

        # Additional statistics
        st.divider()
        st.markdown("#### 詳細統計")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**変更別結果数**")
            # Only count rows with actual search results
            df_with_results = output_df[
                output_df["検索結果_変更"].notna() & (output_df["検索結果_変更"] != "")
            ]
            if not df_with_results.empty:
                change_count = df_with_results.groupby("変更").size().reset_index(name="件数")
                change_count = change_count.sort_values("件数", ascending=False)
                st.dataframe(change_count, width="stretch", hide_index=True)
            else:
                st.info("検索結果がありません")

        with col2:
            st.markdown("**推定不具合上位**")
            # Filter out empty strings as well as NaN
            df_with_defects = output_df[
                output_df["推定不具合_内容"].notna() & (output_df["推定不具合_内容"] != "")
            ]
            if not df_with_defects.empty:
                defects_count = (
                    df_with_defects.groupby("推定不具合_内容")
                    .size()
                    .reset_index(name="件数")
                    .sort_values("件数", ascending=False)
                    .head(10)
                )
                st.dataframe(defects_count, width="stretch", hide_index=True)
            else:
                st.info("推定不具合がありません")

    # --- CSV Download Section ---
    st.subheader("結果のダウンロード")

    # Prepare CSV data
    csv_data = output_df.to_csv(index=False).encode("utf-8-sig")  # UTF-8 with BOM for Excel

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        st.download_button(
            label="結果をCSVでダウンロード",
            data=csv_data,
            file_name="drbfm_results.csv",
            mime="text/csv",
            type="primary",
            width="stretch",
        )


def main():
    st.set_page_config(
        page_title="DRBFMアプリ",
        page_icon="🔍️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Sidebar ---
    with st.sidebar:
        st.title("DRBFMアプリ")

        # New execution button at the top
        if st.button("＋ 新規実行", key="new_execution", use_container_width=True, type="primary"):
            # Clear all execution-related state
            st.session_state.loaded_from_history = False
            st.session_state.results = None
            st.session_state.inputs = None
            st.session_state.change_items = [{"id": str(uuid.uuid4()), "change": ""}]
            # Also clear pending execution state to prevent re-execution
            st.session_state.is_executing = False
            st.session_state.pop("pending_inputs", None)
            st.session_state.pop("pending_top_k", None)
            st.session_state.pop("pending_search_size", None)
            st.rerun()

        # Refresh button
        if st.button("履歴を更新", key="refresh_history", use_container_width=True):
            st.session_state.pop("execution_history", None)
            st.session_state.pop("history_offset", None)
            st.rerun()

        # Fetch and display history
        if "execution_history" not in st.session_state:
            with st.spinner("履歴を読み込み中..."):
                st.session_state.execution_history = asyncio.run(fetch_execution_history(limit=20))
                st.session_state.history_offset = 20

        default_history = {"items": [], "has_more": False, "error": None}
        history_data = st.session_state.get("execution_history", default_history)
        history = history_data.get("items", [])
        history_error = history_data.get("error")
        has_more = history_data.get("has_more", False)

        if history_error:
            st.warning(history_error)
        elif not history:
            st.info("実行履歴がありません")
        else:
            for item in history:
                thread_id = item["thread_id"]
                display_time = item["display_time"]
                change_point = item["change_point"]
                status = item["status"]
                result_count = item["result_count"]
                batch_id = item.get("batch_id")
                batch_count = item.get("batch_count", 1)
                batch_total = item.get("batch_total", batch_count)

                # Status indicator
                status_emoji = {
                    "success": "✅",
                    "error": "❌",
                    "pending": "⏳",
                    "running": "🔄",
                }.get(status, "❓")

                # Truncate change_point for display
                change_preview = change_point[:20] + "..." if len(change_point) > 20 else change_point
                if not change_preview:
                    change_preview = "(入力なし)"

                # Date/time, status, and batch count as header
                if batch_total > 1:
                    # Show progress for running batches, count for completed
                    if status in ("running", "pending") and batch_count < batch_total:
                        st.caption(f"{status_emoji} {display_time} ({batch_count}/{batch_total}件)")
                        help_text = f"バッチ実行中: {batch_count}/{batch_total}件完了"
                    else:
                        st.caption(f"{status_emoji} {display_time} ({batch_total}件)")
                        help_text = f"バッチ実行: {batch_total}件の変更点"
                else:
                    st.caption(f"{status_emoji} {display_time}")
                    help_text = change_point

                # Check if this is a new-style batch thread
                is_new_batch = item.get("is_new_batch", False)

                # Check if workflow is still running
                is_running = status in ("running", "pending")

                # Clickable history card: input content
                if is_running:
                    btn_label = f"🔄 {change_preview} (実行中...)"
                    btn_help = "実行中のため読み込めません。完了までお待ちください。"
                else:
                    # Add "ほか" suffix for batch executions with multiple items
                    if batch_total > 1:
                        btn_label = f"{change_preview} ほか"
                    else:
                        btn_label = change_preview
                    btn_help = help_text

                if st.button(
                    btn_label,
                    key=f"load_{thread_id}",
                    use_container_width=True,
                    help=btn_help,
                    disabled=is_running,
                ):
                    if is_new_batch:
                        # New-style batch: load directly from thread
                        st.session_state.loading_new_batch_thread_id = thread_id
                    elif batch_id and batch_count > 1:
                        # Old-style batch: load by batch_id
                        st.session_state.loading_batch_id = batch_id
                    else:
                        # Single thread
                        st.session_state.loading_thread_id = thread_id
                    st.rerun()

            # "Load more" button for pagination
            if has_more:
                if st.button("もっと読み込む", key="load_more_history", use_container_width=True):
                    with st.spinner("追加の履歴を読み込み中..."):
                        offset = st.session_state.get("history_offset", 20)
                        more_data = asyncio.run(fetch_execution_history(limit=20, offset=offset))
                        if more_data.get("items"):
                            # Append new items to existing history
                            current_history = st.session_state.execution_history
                            current_history["items"].extend(more_data["items"])
                            current_history["has_more"] = more_data.get("has_more", False)
                            st.session_state.execution_history = current_history
                            st.session_state.history_offset = offset + 20
                        else:
                            st.session_state.execution_history["has_more"] = False
                    st.rerun()

    # --- Handle loading new-style batch from history ---
    if "loading_new_batch_thread_id" in st.session_state:
        thread_id = st.session_state.loading_new_batch_thread_id
        with st.spinner("バッチ履歴を読み込み中..."):
            result = asyncio.run(load_thread_results(thread_id))
            if result:
                # Extract results from per_cp_results
                change_points = result.get("change_points", [])
                per_cp_results = result.get("per_cp_results", [])
                if change_points and per_cp_results:
                    # New-style batch: use per_cp_results directly
                    st.session_state.results = per_cp_results
                    st.session_state.inputs = [{"change": cp} for cp in change_points]
                    st.session_state.loaded_from_history = True
                    st.toast("結果を読み込みました", icon="✅")
                else:
                    st.toast("バッチデータの形式が不正です", icon="❌")
            else:
                st.toast("読み込みに失敗しました", icon="❌")
        del st.session_state.loading_new_batch_thread_id

    # --- Handle loading old-style batch from history ---
    elif "loading_batch_id" in st.session_state:
        batch_id = st.session_state.loading_batch_id
        with st.spinner("バッチ履歴を読み込み中..."):
            batch_results = asyncio.run(load_batch_results(batch_id))
            if batch_results:
                # Extract results and inputs from batch
                results = [item["values"] for item in batch_results]
                inputs = [{"change": item["change_point"]} for item in batch_results]
                st.session_state.results = results
                st.session_state.inputs = inputs
                st.session_state.loaded_from_history = True
                st.toast("結果を読み込みました", icon="✅")
            else:
                st.toast("読み込みに失敗しました", icon="❌")
        del st.session_state.loading_batch_id

    # --- Handle loading single thread from history ---
    elif "loading_thread_id" in st.session_state:
        thread_id = st.session_state.loading_thread_id
        with st.spinner("履歴を読み込み中..."):
            result = asyncio.run(load_thread_results(thread_id))
            if result:
                change_point = result.get("change_point", "")
                # Set results and inputs from loaded thread
                st.session_state.results = [result]
                st.session_state.inputs = [{"change": change_point}]
                st.session_state.loaded_from_history = True
                st.toast("結果を読み込みました", icon="✅")
            else:
                st.toast("読み込みに失敗しました", icon="❌")
        del st.session_state.loading_thread_id

    # Initialize session state for dynamic form
    if "change_items" not in st.session_state:
        st.session_state.change_items = [{"id": str(uuid.uuid4()), "change": ""}]

    if "results" not in st.session_state:
        st.session_state.results = None

    if "inputs" not in st.session_state:
        st.session_state.inputs = None

    if "loaded_from_history" not in st.session_state:
        st.session_state.loaded_from_history = False

    if "is_executing" not in st.session_state:
        st.session_state.is_executing = False

    # --- Main Content ---
    if not st.session_state.loaded_from_history:
        # New execution mode: show input form
        execute_button, inputs_to_process, top_k, search_size = render_input_form()

        # Handle workflow execution
        if execute_button and not st.session_state.is_executing:
            # Get inputs from form if CSV not used
            if not inputs_to_process:
                inputs_to_process = [
                    {"change": item["change"]}
                    for item in st.session_state.change_items
                    if item["change"].strip()
                ]

            if not inputs_to_process:
                st.warning("処理する変更点がありません。フォームに入力するか、CSVをアップロードしてください")
            else:
                # バリデーション実行
                change_texts = [item["change"] for item in inputs_to_process]
                validation_result = validate_change_points(change_texts)

                # エラー表示（最初の5件のみ）
                max_displayed_errors = 5
                if len(validation_result.errors) > max_displayed_errors:
                    for error in validation_result.errors[:max_displayed_errors]:
                        st.error(error)
                    remaining = len(validation_result.errors) - max_displayed_errors
                    st.error(f"他 {remaining} 件のエラーがあります")
                else:
                    for error in validation_result.errors:
                        st.error(error)

                # 警告表示
                for warning in validation_result.warnings:
                    st.warning(warning)
                    st.toast(warning, icon="⚠️")

                if validation_result.is_valid:
                    # Store execution parameters in session state and set executing flag
                    st.session_state.is_executing = True
                    st.session_state.pending_inputs = inputs_to_process
                    st.session_state.pending_top_k = top_k
                    st.session_state.pending_search_size = search_size
                    st.rerun()

        # Execute workflow if pending
        if st.session_state.is_executing and "pending_inputs" in st.session_state:
            pending_inputs = st.session_state.pop("pending_inputs")
            pending_top_k = st.session_state.pop("pending_top_k", 5)
            pending_search_size = st.session_state.pop("pending_search_size", 10)

            # Clear executing flag immediately to prevent re-execution
            st.session_state.is_executing = False

            # Show start toast
            st.toast(f"ワークフローを実行開始しました（{len(pending_inputs)}件）", icon="🚀")

            # Generate batch_id for grouping multiple change points
            batch_id = str(uuid.uuid4())

            # Run all workflows in parallel
            with st.spinner(f"ワークフロー実行中... ({len(pending_inputs)}件)"):
                results = asyncio.run(
                    run_drbfm_workflows_batch(
                        changes=pending_inputs,
                        top_k=pending_top_k,
                        search_size=pending_search_size,
                        batch_id=batch_id,
                    )
                )

            # Store results in session state
            st.session_state.results = results
            st.session_state.inputs = pending_inputs

            st.toast(f"ワークフローの実行が完了しました（{len(pending_inputs)}件）", icon="✅")

            # Rerun to refresh UI (button state, etc.)
            st.rerun()

    # --- Output Display (shown in both modes) ---
    render_results()


if __name__ == "__main__":
    main()
