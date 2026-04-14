"""Responsive design utilities for Streamlit.

This module provides helper functions for implementing responsive layouts
within Streamlit's constraints. Since Streamlit doesn't support CSS classes
on native widgets, we use wrapper components and CSS custom properties.

Breakpoints:
    - Desktop: 1024px and above (default)
    - Tablet: 768px - 1023px
    - Mobile: below 768px
"""

from __future__ import annotations

from typing import Any, Literal

import streamlit as st

# Breakpoint values (pixels)
BREAKPOINT_MOBILE = 767
BREAKPOINT_TABLET = 1023
BREAKPOINT_DESKTOP = 1024

# CSS class constants
CSS_CLASS_CONTAINER = "pfmea-container"
CSS_CLASS_ROW = "pfmea-row"
CSS_CLASS_COL = "pfmea-col"
CSS_CLASS_METRICS_GRID = "pfmea-metrics-grid"
CSS_CLASS_HEADER_ROW = "pfmea-header-row"
CSS_CLASS_SELECTOR_ROW = "pfmea-selector-row"
CSS_CLASS_TABLE_RESPONSIVE = "pfmea-table-responsive"


def responsive_container(content: str, *, css_class: str = CSS_CLASS_CONTAINER) -> str:
    """Wrap content in a responsive container div.

    Args:
        content: HTML content to wrap.
        css_class: CSS class for the container (default: pfmea-container).

    Returns:
        HTML string with wrapped content.

    Example:
        >>> html = responsive_container("<p>Content</p>")
        >>> st.markdown(html, unsafe_allow_html=True)
    """
    return f'<div class="{css_class}">{content}</div>'


def responsive_table_wrapper(table_html: str) -> str:
    """Wrap a table in a responsive scrollable container.

    Enables horizontal scrolling on narrow screens while maintaining
    table readability. Adds touch-friendly scrolling on mobile.

    Args:
        table_html: HTML table content.

    Returns:
        HTML string with wrapped table.
    """
    return f'<div class="{CSS_CLASS_TABLE_RESPONSIVE}">{table_html}</div>'


def metrics_grid_html(metrics: list[dict[str, Any]]) -> str:
    """Generate HTML for a responsive metrics grid.

    Creates a grid layout that adjusts columns based on screen size:
    - Desktop: 5 columns
    - Tablet: 3 columns
    - Mobile: 2 columns

    Args:
        metrics: List of metric dictionaries with 'label' and 'value' keys.

    Returns:
        HTML string for the metrics grid.
    """
    items = []
    for metric in metrics:
        label = metric.get("label", "")
        value = metric.get("value", "")
        delta = metric.get("delta", "")
        delta_html = f'<span class="metric-delta">{delta}</span>' if delta else ""
        items.append(
            f'<div class="metric-item">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div>'
            f"{delta_html}"
            f"</div>"
        )
    return f'<div class="{CSS_CLASS_METRICS_GRID}">{"".join(items)}</div>'


def get_responsive_columns(
    layout: Literal["header", "selector", "pagination", "metrics"],
) -> list[int | float]:
    """Get column ratios for common layout patterns.

    Provides consistent column ratios across the application.
    These ratios work well with Streamlit's st.columns().

    Args:
        layout: Layout pattern name.
            - "header": Title + Stats + Action (2:3:1)
            - "selector": Select + Display (2:1)
            - "pagination": Input + Caption + Size (1:2:1)
            - "metrics": 5 equal columns

    Returns:
        List of column ratios for st.columns().

    Example:
        >>> cols = st.columns(get_responsive_columns("header"))
        >>> cols[0].subheader("Title")
        >>> cols[1].caption("Stats")
        >>> cols[2].button("Action")
    """
    patterns: dict[str, list[int | float]] = {
        "header": [2, 3, 1],
        "selector": [2, 1],
        "pagination": [1, 2, 1],
        "metrics": [1, 1, 1, 1, 1],
    }
    return patterns.get(layout, [1])


def inject_responsive_styles() -> None:
    """Inject additional responsive CSS for Streamlit widgets.

    Call this function once per page to add responsive overrides
    for Streamlit's native widgets (buttons, inputs, etc.).

    This supplements the base.css with Streamlit-specific selectors
    that can't be easily targeted in external CSS.
    """
    responsive_css = """
    <style>
    /* Streamlit-specific responsive overrides */

    /* Button responsiveness */
    @media screen and (max-width: 767px) {
        [data-testid="stButton"] > button {
            width: 100%;
            padding: var(--pfmea-spacing-sm) var(--pfmea-spacing-md);
        }

        /* Column stacking hint for small screens */
        [data-testid="column"] {
            min-width: 100% !important;
        }

        /* Reduce metric padding on mobile */
        [data-testid="stMetric"] {
            padding: var(--pfmea-spacing-xs);
        }

        [data-testid="stMetricLabel"] {
            font-size: var(--pfmea-font-size-xs);
        }
    }

    /* Tablet adjustments */
    @media screen and (max-width: 1023px) and (min-width: 768px) {
        [data-testid="stMetric"] {
            padding: var(--pfmea-spacing-sm);
        }
    }

    /* Expander content padding */
    [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
        padding-top: var(--pfmea-spacing-sm);
    }

    /* Selectbox responsive width */
    @media screen and (max-width: 767px) {
        [data-testid="stSelectbox"] {
            width: 100%;
        }
    }
    </style>
    """
    st.markdown(responsive_css, unsafe_allow_html=True)


__all__ = [
    "BREAKPOINT_DESKTOP",
    "BREAKPOINT_MOBILE",
    "BREAKPOINT_TABLET",
    "CSS_CLASS_CONTAINER",
    "CSS_CLASS_HEADER_ROW",
    "CSS_CLASS_METRICS_GRID",
    "CSS_CLASS_ROW",
    "CSS_CLASS_SELECTOR_ROW",
    "CSS_CLASS_TABLE_RESPONSIVE",
    "get_responsive_columns",
    "inject_responsive_styles",
    "metrics_grid_html",
    "responsive_container",
    "responsive_table_wrapper",
]
