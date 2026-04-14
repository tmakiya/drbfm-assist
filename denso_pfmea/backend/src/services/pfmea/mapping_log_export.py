"""PFMEA Mapping Log Export Utilities

This module provides utilities to export PFMEA mapping logs to CSV format for debugging and analysis.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from .mapping_logger import get_mapping_logger

logger = logging.getLogger(__name__)


def export_mapping_logs_to_csv() -> str | None:
    """Export current session's mapping logs to CSV format.

    Returns:
        CSV string if logs exist, None otherwise
    """
    mapping_logger = get_mapping_logger()

    if len(mapping_logger) == 0:
        logger.info("No mapping logs to export")
        return None

    # Get CSV content
    csv_content = mapping_logger.export_to_csv()

    # Log statistics
    stats = mapping_logger.get_summary_statistics()
    logger.info(
        "Exporting %d mapping log entries. By type: %s",
        stats["total_corrections"],
        stats["by_correction_type"],
    )

    return csv_content


def display_mapping_log_download_button(container: Any = None) -> None:
    """Display a download button for mapping logs in Streamlit UI.

    Args:
        container: Streamlit container to place the button (defaults to st)
    """
    if container is None:
        container = st

    mapping_logger = get_mapping_logger()

    if len(mapping_logger) == 0:
        return

    # Get log statistics
    stats = mapping_logger.get_summary_statistics()

    # Display download button
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pfmea_mapping_logs_{timestamp}.csv"

    csv_content = mapping_logger.export_to_csv()

    columns_func = getattr(container, "columns", None)
    if columns_func is None:
        columns_func = st.columns
    col1, col2 = columns_func([3, 1])

    info_func = getattr(col1, "info", st.info)
    info_func(
        f"⚠️ マッピング処理で{stats['total_corrections']}件のインデックス補正が発生しました。"
        f" 詳細ログをダウンロードして確認してください。"
    )

    download_button = getattr(col2, "download_button", st.download_button)
    download_button(
        label="📊 詳細ログをダウンロード",
        data=csv_content,
        file_name=filename,
        mime="text/csv",
        help=(
            f"補正タイプ別: {stats['by_correction_type']}\n"
            f"フィールド別: {stats['by_field']}"
        ),
    )


def get_mapping_logs_dataframe() -> pd.DataFrame | None:
    """Get current mapping logs as a DataFrame for display.

    Returns:
        DataFrame with mapping logs or None if no logs exist
    """
    mapping_logger = get_mapping_logger()

    if len(mapping_logger) == 0:
        return None

    return mapping_logger.get_logs_as_dataframe()


def clear_mapping_logs() -> None:
    """Clear all current mapping logs."""
    mapping_logger = get_mapping_logger()
    mapping_logger.clear_logs()
    logger.info("Mapping logs cleared")
