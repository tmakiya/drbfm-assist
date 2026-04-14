"""Accessibility utilities for PFMEA UI.

This module provides helper functions for implementing accessibility features
following WCAG 2.1 guidelines. It includes utilities for ARIA attributes,
screen reader support, and keyboard navigation.

Guidelines Reference:
- WCAG 2.1 AA compliance target
- Color contrast ratio: 4.5:1 for normal text, 3:1 for large text
- Minimum touch target: 44x44px
"""

from __future__ import annotations

from typing import Any

import streamlit as st

# ARIA role constants
ROLE_GRID = "grid"
ROLE_ROW = "row"
ROLE_GRIDCELL = "gridcell"
ROLE_COLUMNHEADER = "columnheader"
ROLE_PROGRESSBAR = "progressbar"
ROLE_STATUS = "status"
ROLE_ALERT = "alert"
ROLE_REGION = "region"

# CSS class constants
CSS_SR_ONLY = "pfmea-sr-only"
CSS_SKIP_LINK = "pfmea-skip-link"
CSS_TOUCH_TARGET = "pfmea-touch-target"


def sr_only(text: str) -> str:
    """Wrap text in a screen-reader-only span.

    The text will be read by screen readers but visually hidden.
    Use this for providing additional context to assistive technologies.

    Args:
        text: Text content for screen readers.

    Returns:
        HTML span element with sr-only class.

    Example:
        >>> html = sr_only("Current page: ")
        >>> st.markdown(html + "Dashboard", unsafe_allow_html=True)
    """
    return f'<span class="{CSS_SR_ONLY}">{text}</span>'


def aria_live_region(
    content: str,
    *,
    politeness: str = "polite",
    atomic: bool = True,
) -> str:
    """Create an ARIA live region for dynamic content announcements.

    Live regions notify screen reader users of content changes without
    requiring focus change.

    Args:
        content: The content to announce.
        politeness: "polite" (waits for pause) or "assertive" (interrupts).
        atomic: If True, announces the entire region on change.

    Returns:
        HTML div with aria-live attributes.

    Example:
        >>> html = aria_live_region("Analysis complete", politeness="polite")
        >>> st.markdown(html, unsafe_allow_html=True)
    """
    atomic_attr = "true" if atomic else "false"
    return (
        f'<div role="{ROLE_STATUS}" aria-live="{politeness}" '
        f'aria-atomic="{atomic_attr}" class="pfmea-status">{content}</div>'
    )


def progress_bar_attrs(
    value: int,
    *,
    min_value: int = 0,
    max_value: int = 100,
    label: str = "Progress",
) -> dict[str, Any]:
    """Generate accessible attributes for a progress bar.

    Returns a dictionary of attributes to add to a progress bar element
    for screen reader compatibility.

    Args:
        value: Current progress value.
        min_value: Minimum value (default: 0).
        max_value: Maximum value (default: 100).
        label: Accessible label for the progress bar.

    Returns:
        Dictionary of ARIA attributes.

    Example:
        >>> attrs = progress_bar_attrs(50, label="Loading data")
        >>> # Use attrs in custom HTML rendering
    """
    return {
        "role": ROLE_PROGRESSBAR,
        "aria-valuenow": str(value),
        "aria-valuemin": str(min_value),
        "aria-valuemax": str(max_value),
        "aria-label": label,
    }


def table_attrs(label: str) -> dict[str, str]:
    """Generate accessible attributes for a data table.

    Args:
        label: Accessible label describing the table contents.

    Returns:
        Dictionary of ARIA attributes for the table element.
    """
    return {
        "role": ROLE_GRID,
        "aria-label": label,
    }


def inject_accessibility_styles() -> None:
    """Inject accessibility-enhancing CSS for Streamlit widgets.

    Call this function once per page to add accessibility overrides
    for Streamlit's native widgets. This supplements base.css with
    Streamlit-specific selectors.
    """
    a11y_css = """
    <style>
    /* Enhanced focus indicators for Streamlit widgets */
    [data-testid="stButton"] > button:focus-visible,
    [data-testid="stSelectbox"] > div:focus-visible,
    [data-testid="stTextInput"] > div > input:focus-visible {
        outline: 2px solid var(--pfmea-primary, #1976D2);
        outline-offset: 2px;
    }

    /* Ensure sufficient color contrast for disabled states */
    [data-testid="stButton"] > button:disabled {
        opacity: 0.6;
    }

    /* Progress bar accessibility */
    [data-testid="stProgress"] > div {
        position: relative;
    }

    /* Metric labels - ensure readability */
    [data-testid="stMetricLabel"] {
        font-weight: var(--pfmea-font-weight-medium, 500);
    }

    /* Table header scope indication */
    [data-testid="stDataFrame"] th {
        font-weight: var(--pfmea-font-weight-semibold, 600);
    }

    /* Alert role for error/warning/info messages */
    [data-testid="stAlert"] {
        role: alert;
    }
    </style>
    """
    st.markdown(a11y_css, unsafe_allow_html=True)


def skip_link(target_id: str, label: str = "Skip to main content") -> str:
    """Create a skip link for keyboard navigation.

    Skip links allow keyboard users to bypass repetitive navigation
    and jump directly to the main content.

    Args:
        target_id: ID of the element to skip to.
        label: Visible label for the skip link.

    Returns:
        HTML anchor element styled as a skip link.

    Example:
        >>> html = skip_link("main-content", "Skip to analysis results")
        >>> st.markdown(html, unsafe_allow_html=True)
    """
    return f'<a href="#{target_id}" class="{CSS_SKIP_LINK}">{label}</a>'


def landmark_region(content: str, *, label: str, tag: str = "section") -> str:
    """Wrap content in a landmark region with an accessible name.

    Landmark regions help screen reader users navigate page sections.

    Args:
        content: HTML content to wrap.
        label: Accessible name for the region.
        tag: HTML tag to use (section, nav, main, aside, etc.).

    Returns:
        HTML with landmark region wrapper.
    """
    return f'<{tag} role="{ROLE_REGION}" aria-label="{label}">{content}</{tag}>'


__all__ = [
    "CSS_SKIP_LINK",
    "CSS_SR_ONLY",
    "CSS_TOUCH_TARGET",
    "ROLE_ALERT",
    "ROLE_COLUMNHEADER",
    "ROLE_GRID",
    "ROLE_GRIDCELL",
    "ROLE_PROGRESSBAR",
    "ROLE_REGION",
    "ROLE_ROW",
    "ROLE_STATUS",
    "aria_live_region",
    "inject_accessibility_styles",
    "landmark_region",
    "progress_bar_attrs",
    "skip_link",
    "sr_only",
    "table_attrs",
]
