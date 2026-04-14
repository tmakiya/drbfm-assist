"""Design system for PFMEA UI.

This module provides centralized design tokens (colors, typography, spacing)
for consistent styling across the application.

Usage:
    from src.ui.design_system import colors, typography, spacing
    from src.ui.design_system import apply_base_styles

    # In your Streamlit app
    apply_base_styles()

    # Access tokens
    primary_color = colors.PRIMARY
    font_family = typography.FONT_FAMILY_PRIMARY
"""

from __future__ import annotations

from .accessibility import (
    CSS_SKIP_LINK,
    CSS_SR_ONLY,
    CSS_TOUCH_TARGET,
    ROLE_ALERT,
    ROLE_GRID,
    ROLE_PROGRESSBAR,
    ROLE_STATUS,
    aria_live_region,
    inject_accessibility_styles,
    landmark_region,
    progress_bar_attrs,
    skip_link,
    sr_only,
    table_attrs,
)
from .responsive import (
    BREAKPOINT_DESKTOP,
    BREAKPOINT_MOBILE,
    BREAKPOINT_TABLET,
    get_responsive_columns,
    inject_responsive_styles,
    responsive_container,
    responsive_table_wrapper,
)
from .style_provider import (
    apply_base_styles,
    get_ai_row_color,
    get_table_style_block,
    get_table_styles,
    styled_markdown,
)
from .tokens import (
    border_radius,
    colors,
    dark_colors,
    shadows,
    spacing,
    transitions,
    typography,
)

__all__ = [
    # Style provider functions
    "apply_base_styles",
    "get_table_styles",
    "get_table_style_block",
    "get_ai_row_color",
    "styled_markdown",
    # Responsive utilities
    "BREAKPOINT_DESKTOP",
    "BREAKPOINT_MOBILE",
    "BREAKPOINT_TABLET",
    "get_responsive_columns",
    "inject_responsive_styles",
    "responsive_container",
    "responsive_table_wrapper",
    # Accessibility utilities
    "CSS_SKIP_LINK",
    "CSS_SR_ONLY",
    "CSS_TOUCH_TARGET",
    "ROLE_ALERT",
    "ROLE_GRID",
    "ROLE_PROGRESSBAR",
    "ROLE_STATUS",
    "aria_live_region",
    "inject_accessibility_styles",
    "landmark_region",
    "progress_bar_attrs",
    "skip_link",
    "sr_only",
    "table_attrs",
    # Token instances
    "colors",
    "dark_colors",
    "spacing",
    "typography",
    "shadows",
    "border_radius",
    "transitions",
]
