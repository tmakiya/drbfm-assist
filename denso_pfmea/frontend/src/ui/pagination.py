"""Pagination utilities for Streamlit DataFrames.

Provides reusable pagination components for displaying large DataFrames
in manageable chunks, improving performance and user experience.
"""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st


def paginated_dataframe(
    df: pd.DataFrame,
    *,
    page_size: int = 100,
    key_prefix: str = "paginated_df",
    height: int | Literal["auto"] | None = None,
    use_container_width: bool = True,
    hide_index: bool = True,
    column_config: dict[str, Any] | None = None,
) -> None:
    """Display a DataFrame with pagination controls.

    Automatically adds pagination UI when DataFrame exceeds page_size rows.
    For smaller DataFrames, displays without pagination.

    Args:
        df: DataFrame to display
        page_size: Number of rows per page (default: 100)
        key_prefix: Unique prefix for widget keys (prevents conflicts)
        height: Optional fixed height for the dataframe display
        use_container_width: Whether to use full container width
        hide_index: Whether to hide the DataFrame index
        column_config: Optional column configuration dict

    Example:
        >>> df = pd.DataFrame({'col': range(1000)})
        >>> paginated_dataframe(df, page_size=50, key_prefix="my_table")
    """
    if df.empty:
        st.info("データがありません。")
        return

    total_rows = len(df)

    # If DataFrame is small enough, display without pagination
    if total_rows <= page_size:
        kwargs: dict[str, Any] = {
            "use_container_width": use_container_width,
            "hide_index": hide_index,
        }
        if height is not None:
            kwargs["height"] = height
        if column_config is not None:
            kwargs["column_config"] = column_config
        st.dataframe(df, **kwargs)
        return

    # Calculate pagination
    total_pages = (total_rows - 1) // page_size + 1

    # Pagination controls
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        current_page = st.number_input(
            "ページ",
            min_value=1,
            max_value=total_pages,
            value=1,
            key=f"{key_prefix}_page_number",
            help=f"全{total_pages}ページ",
        )

    with col2:
        st.caption(
            f"全{total_rows:,}行中 {(current_page - 1) * page_size + 1:,}-"
            f"{min(current_page * page_size, total_rows):,}行を表示"
        )

    with col3:
        page_size_options = [50, 100, 200, 500]
        if page_size not in page_size_options:
            page_size_options.append(page_size)
            page_size_options.sort()

        selected_page_size = st.selectbox(
            "表示件数",
            options=page_size_options,
            index=page_size_options.index(page_size),
            key=f"{key_prefix}_page_size",
        )

        # Update page_size if changed
        if selected_page_size != page_size:
            page_size = selected_page_size
            # Recalculate current page to show same data
            total_pages = (total_rows - 1) // page_size + 1
            if current_page > total_pages:
                current_page = total_pages

    # Calculate slice indices
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)

    # Display paginated dataframe
    kwargs = {
        "use_container_width": use_container_width,
        "hide_index": hide_index,
    }
    if height is not None:
        kwargs["height"] = height
    if column_config is not None:
        kwargs["column_config"] = column_config
    st.dataframe(df.iloc[start_idx:end_idx], **kwargs)


def paginated_table(
    df: pd.DataFrame,
    *,
    page_size: int = 50,
    key_prefix: str = "paginated_table",
) -> None:
    """Display a DataFrame as a static table with pagination.

    Unlike paginated_dataframe, this uses st.table for a non-interactive
    display that's better suited for small tables with custom styling.

    Args:
        df: DataFrame to display
        page_size: Number of rows per page (default: 50, smaller for tables)
        key_prefix: Unique prefix for widget keys

    Example:
        >>> df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
        >>> paginated_table(df, page_size=2)
    """
    if df.empty:
        st.info("データがありません。")
        return

    total_rows = len(df)

    # If DataFrame is small enough, display without pagination
    if total_rows <= page_size:
        st.table(df)
        return

    # Calculate pagination
    total_pages = (total_rows - 1) // page_size + 1

    # Pagination controls
    col1, col2 = st.columns([1, 3])

    with col1:
        current_page = st.number_input(
            "ページ",
            min_value=1,
            max_value=total_pages,
            value=1,
            key=f"{key_prefix}_page_number",
        )

    with col2:
        st.caption(
            f"全{total_rows}行中 {(current_page - 1) * page_size + 1}-{min(current_page * page_size, total_rows)}行を表示（全{total_pages}ページ）"
        )

    # Calculate slice indices
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)

    # Display paginated table
    st.table(df.iloc[start_idx:end_idx])


def get_page_slice(
    total_items: int,
    page_size: int,
    current_page: int = 1,
) -> tuple[int, int]:
    """Calculate start and end indices for a pagination slice.

    Utility function for custom pagination implementations.

    Args:
        total_items: Total number of items
        page_size: Items per page
        current_page: Current page number (1-indexed)

    Returns:
        Tuple of (start_index, end_index) for slicing (0-indexed, exclusive end)

    Example:
        >>> start, end = get_page_slice(1000, 100, 3)
        >>> items_page_3 = all_items[start:end]
    """
    # Ensure page is within valid range
    total_pages = max(1, (total_items - 1) // page_size + 1)
    current_page = max(1, min(current_page, total_pages))

    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)

    return start_idx, end_idx


__all__ = [
    "paginated_dataframe",
    "paginated_table",
    "get_page_slice",
]
