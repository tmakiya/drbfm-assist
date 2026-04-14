"""Style provider for applying design system styles in Streamlit.

This module provides utilities for injecting CSS and design tokens
into Streamlit applications.

Usage:
    from src.ui.design_system import apply_base_styles

    # In your Streamlit app
    apply_base_styles()
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import streamlit as st

from .tokens import colors, spacing, typography

# Cache the CSS file content
_CSS_CACHE: dict[str, str] = {}

ThemeMode = Literal["light", "dark", "auto"]


def _get_base_css() -> str:
    """Load the base CSS file content.

    Returns:
        CSS content as string.
    """
    if "base" not in _CSS_CACHE:
        css_path = Path(__file__).parent.parent / "styles" / "base.css"
        if css_path.exists():
            _CSS_CACHE["base"] = css_path.read_text(encoding="utf-8")
        else:
            # Fallback: generate minimal CSS from tokens
            _CSS_CACHE["base"] = _generate_css_from_tokens()
    return _CSS_CACHE["base"]


def _generate_css_from_tokens() -> str:
    """Generate CSS custom properties from design tokens.

    Used as fallback when base.css is not available.

    Returns:
        Generated CSS string.
    """
    parts = [
        colors.to_css_variables(),
        typography.to_css_variables(),
        spacing.to_css_variables(),
    ]
    return "\n\n".join(parts)


def apply_base_styles(*, theme_mode: ThemeMode = "auto") -> None:
    """Apply base design system styles to the Streamlit app.

    This function should be called early in the app initialization,
    typically after st.set_page_config().

    Args:
        theme_mode: Theme mode to apply. "auto" uses browser preference.

    Example:
        st.set_page_config(page_title="PFMEA", layout="wide")
        apply_base_styles()
    """
    css = _get_base_css()

    # Add theme class based on mode
    if theme_mode == "dark":
        css += """
        <script>
        document.documentElement.setAttribute('data-theme', 'dark');
        </script>
        """
    elif theme_mode == "auto":
        css += """
        <script>
        (function() {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (prefersDark) {
                document.documentElement.setAttribute('data-theme', 'dark');
            }
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
            });
        })();
        </script>
        """

    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def get_table_styles() -> list[dict[str, object]]:
    """Get table styles as a list of style dictionaries.

    Compatible with pandas Styler and existing PFMEA_TABLE_STYLES format.

    Returns:
        List of style dictionaries for table styling.
    """
    return [
        {
            "selector": "table",
            "props": [
                ("border-collapse", "collapse"),
                ("width", "100%"),
                ("font-size", "13px"),
                ("font-family", typography.FONT_FAMILY_PRIMARY),
                ("table-layout", "fixed"),
            ],
        },
        {
            "selector": "th, td",
            "props": [
                ("border", f"1px solid {colors.TABLE_BORDER}"),
                ("padding", spacing.TABLE_CELL_PADDING),
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
                ("z-index", "2"),
            ],
        },
    ]


def get_table_style_block() -> str:
    """Get the table container style block as HTML.

    Compatible with existing PFMEA_TABLE_STYLE_BLOCK format.

    Returns:
        HTML style block string.
    """
    return f"""
<style>
.pfmea-ai-table-container {{
  max-height: 520px;
  overflow-y: auto;
  border: 1px solid {colors.TABLE_CONTAINER_BORDER};
  border-radius: 4px;
  margin-bottom: 16px;
}}
.pfmea-ai-table tbody tr:nth-child(even) td {{
  background-color: {colors.TABLE_ROW_EVEN};
}}
</style>
"""


def get_ai_row_color() -> str:
    """Get the color for AI-generated rows.

    Returns:
        Hex color string for AI-generated content.
    """
    return colors.PFMEA_AI_GENERATED


def styled_markdown(
    content: str,
    *,
    variant: Literal["primary", "secondary", "caption", "error"] = "primary",
) -> None:
    """Render styled markdown text.

    Args:
        content: Markdown content to render.
        variant: Text style variant.
    """
    color_map = {
        "primary": colors.TEXT_PRIMARY,
        "secondary": colors.TEXT_SECONDARY,
        "caption": colors.TEXT_SECONDARY,
        "error": colors.ERROR,
    }
    color = color_map.get(variant, colors.TEXT_PRIMARY)
    st.markdown(
        f'<span style="color: {color};">{content}</span>', unsafe_allow_html=True
    )


__all__ = [
    "apply_base_styles",
    "get_table_styles",
    "get_table_style_block",
    "get_ai_row_color",
    "styled_markdown",
    "ThemeMode",
]
