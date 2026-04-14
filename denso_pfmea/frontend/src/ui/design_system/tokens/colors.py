"""Color tokens for PFMEA UI design system.

This module defines the complete color palette for both light and dark themes.
All color values should be referenced from here to ensure consistency.

Usage:
    from src.ui.design_system.tokens import colors

    # Access color values
    primary = colors.PRIMARY
    error_bg = colors.ERROR_LIGHT
"""

from __future__ import annotations


class Colors:
    """Design system color tokens for light theme.

    Color naming follows Material Design conventions with semantic naming
    for application-specific uses.
    """

    # Primary palette (Blue)
    PRIMARY_50: str = "#E3F2FD"
    PRIMARY_100: str = "#BBDEFB"
    PRIMARY_200: str = "#90CAF9"
    PRIMARY_300: str = "#64B5F6"
    PRIMARY_400: str = "#42A5F5"
    PRIMARY_500: str = "#2196F3"
    PRIMARY_600: str = "#1E88E5"
    PRIMARY_700: str = "#1976D2"
    PRIMARY_800: str = "#1565C0"
    PRIMARY_900: str = "#0D47A1"

    # Aliases for common primary usage
    PRIMARY: str = PRIMARY_700
    PRIMARY_LIGHT: str = PRIMARY_400
    PRIMARY_DARK: str = PRIMARY_800

    # Secondary palette (Purple)
    SECONDARY_50: str = "#F3E5F5"
    SECONDARY_100: str = "#E1BEE7"
    SECONDARY_200: str = "#CE93D8"
    SECONDARY_300: str = "#BA68C8"
    SECONDARY_400: str = "#AB47BC"
    SECONDARY_500: str = "#9C27B0"
    SECONDARY_600: str = "#8E24AA"
    SECONDARY_700: str = "#7B1FA2"
    SECONDARY_800: str = "#6A1B9A"
    SECONDARY_900: str = "#4A148C"

    SECONDARY: str = SECONDARY_700
    SECONDARY_LIGHT: str = SECONDARY_300
    SECONDARY_DARK: str = SECONDARY_800

    # Accent (Amber/Orange)
    ACCENT: str = "#FF6F00"
    ACCENT_LIGHT: str = "#FFB74D"
    ACCENT_DARK: str = "#E65100"

    # Semantic colors - Success (Green)
    SUCCESS_50: str = "#E8F5E9"
    SUCCESS_100: str = "#C8E6C9"
    SUCCESS_200: str = "#A5D6A7"
    SUCCESS_300: str = "#81C784"
    SUCCESS_400: str = "#66BB6A"
    SUCCESS_500: str = "#4CAF50"
    SUCCESS_600: str = "#43A047"
    SUCCESS_700: str = "#388E3C"
    SUCCESS_800: str = "#2E7D32"
    SUCCESS_900: str = "#1B5E20"

    SUCCESS: str = SUCCESS_800
    SUCCESS_LIGHT: str = SUCCESS_200

    # Semantic colors - Warning (Orange)
    WARNING_50: str = "#FFF3E0"
    WARNING_100: str = "#FFE0B2"
    WARNING_200: str = "#FFCC80"
    WARNING_300: str = "#FFB74D"
    WARNING_400: str = "#FFA726"
    WARNING_500: str = "#FF9800"
    WARNING_600: str = "#FB8C00"
    WARNING_700: str = "#F57C00"
    WARNING_800: str = "#EF6C00"
    WARNING_900: str = "#E65100"

    WARNING: str = WARNING_700
    WARNING_LIGHT: str = WARNING_200

    # Semantic colors - Error (Red)
    ERROR_50: str = "#FFEBEE"
    ERROR_100: str = "#FFCDD2"
    ERROR_200: str = "#EF9A9A"
    ERROR_300: str = "#E57373"
    ERROR_400: str = "#EF5350"
    ERROR_500: str = "#F44336"
    ERROR_600: str = "#E53935"
    ERROR_700: str = "#D32F2F"
    ERROR_800: str = "#C62828"
    ERROR_900: str = "#B71C1C"

    ERROR: str = ERROR_800
    ERROR_LIGHT: str = ERROR_200

    # Semantic colors - Info (Light Blue)
    INFO_50: str = "#E1F5FE"
    INFO_100: str = "#B3E5FC"
    INFO_200: str = "#81D4FA"
    INFO_300: str = "#4FC3F7"
    INFO_400: str = "#29B6F6"
    INFO_500: str = "#03A9F4"
    INFO_600: str = "#039BE5"
    INFO_700: str = "#0288D1"
    INFO_800: str = "#0277BD"
    INFO_900: str = "#01579B"

    INFO: str = INFO_700
    INFO_LIGHT: str = INFO_200

    # Neutral colors (White/Black)
    WHITE: str = "#FFFFFF"
    BLACK: str = "#000000"

    # Gray scale
    GRAY_50: str = "#FAFAFA"
    GRAY_100: str = "#F5F5F5"
    GRAY_200: str = "#EEEEEE"
    GRAY_300: str = "#E0E0E0"
    GRAY_400: str = "#BDBDBD"
    GRAY_500: str = "#9E9E9E"
    GRAY_600: str = "#757575"
    GRAY_700: str = "#616161"
    GRAY_800: str = "#424242"
    GRAY_900: str = "#212121"

    # Surface colors (backgrounds)
    SURFACE: str = WHITE
    SURFACE_VARIANT: str = GRAY_100
    BACKGROUND: str = GRAY_50

    # Text colors
    TEXT_PRIMARY: str = GRAY_900
    TEXT_SECONDARY: str = "#5F5F5F"  # Increased contrast (7.0:1 on white)
    TEXT_DISABLED: str = "#949494"  # Softer disabled tone, >3.0:1 on white
    TEXT_ON_PRIMARY: str = WHITE
    TEXT_ON_ERROR: str = WHITE
    TEXT_ON_SUCCESS: str = WHITE

    # Border colors
    BORDER: str = GRAY_300
    BORDER_LIGHT: str = GRAY_200
    BORDER_FOCUS: str = PRIMARY_700
    BORDER_ERROR: str = ERROR_700

    # PFMEA domain-specific colors
    PFMEA_AI_GENERATED: str = ERROR_700  # #D32F2F - Red for AI-generated rows
    PFMEA_ROW_EVEN: str = "#E8F4F8"  # Light blue for even rows (legacy)
    PFMEA_HEADER: str = GRAY_100  # Table header background

    # Table-specific colors (for backward compatibility)
    TABLE_BORDER: str = "#DDDDDD"  # #ddd from existing code
    TABLE_HEADER_BG: str = GRAY_100  # #f5f5f5
    TABLE_ROW_EVEN: str = GRAY_50  # #fafafa
    TABLE_CONTAINER_BORDER: str = GRAY_300  # #e0e0e0

    def to_css_variables(self) -> str:
        """Generate CSS custom properties from color tokens.

        Returns:
            CSS string with :root variables for all colors.
        """
        lines = [":root {"]
        for attr in dir(self):
            if attr.isupper() and not attr.startswith("_"):
                value = getattr(self, attr)
                if isinstance(value, str) and value.startswith("#"):
                    css_name = attr.lower().replace("_", "-")
                    lines.append(f"  --pfmea-{css_name}: {value};")
        lines.append("}")
        return "\n".join(lines)


class DarkColors:
    """Design system color tokens for dark theme.

    Provides color values optimized for dark backgrounds with appropriate
    contrast ratios for accessibility.
    """

    # Primary palette (adjusted for dark background)
    PRIMARY: str = "#90CAF9"  # Blue 200
    PRIMARY_LIGHT: str = "#BBDEFB"  # Blue 100
    PRIMARY_DARK: str = "#64B5F6"  # Blue 300

    # Secondary palette
    SECONDARY: str = "#CE93D8"  # Purple 200
    SECONDARY_LIGHT: str = "#E1BEE7"  # Purple 100
    SECONDARY_DARK: str = "#BA68C8"  # Purple 300

    # Accent
    ACCENT: str = "#FFB74D"  # Amber 300
    ACCENT_LIGHT: str = "#FFE0B2"  # Amber 100
    ACCENT_DARK: str = "#FFA726"  # Amber 400

    # Semantic colors
    SUCCESS: str = "#81C784"  # Green 300
    SUCCESS_LIGHT: str = "#A5D6A7"  # Green 200
    WARNING: str = "#FFB74D"  # Amber 300
    WARNING_LIGHT: str = "#FFCC80"  # Amber 200
    ERROR: str = "#E57373"  # Red 300
    ERROR_LIGHT: str = "#EF9A9A"  # Red 200
    INFO: str = "#4FC3F7"  # Light Blue 300
    INFO_LIGHT: str = "#81D4FA"  # Light Blue 200

    # Neutral
    WHITE: str = "#FFFFFF"
    BLACK: str = "#000000"

    # Gray scale (inverted for dark mode)
    GRAY_50: str = "#303030"
    GRAY_100: str = "#424242"
    GRAY_200: str = "#616161"
    GRAY_300: str = "#757575"
    GRAY_400: str = "#9E9E9E"
    GRAY_500: str = "#BDBDBD"
    GRAY_600: str = "#E0E0E0"
    GRAY_700: str = "#EEEEEE"
    GRAY_800: str = "#F5F5F5"
    GRAY_900: str = "#FAFAFA"

    # Surface colors
    SURFACE: str = "#121212"
    SURFACE_VARIANT: str = "#1E1E1E"
    BACKGROUND: str = "#0A0A0A"

    # Text colors
    TEXT_PRIMARY: str = "#FFFFFF"
    TEXT_SECONDARY: str = "#B0B0B0"
    TEXT_DISABLED: str = "#6B6B6B"
    TEXT_ON_PRIMARY: str = BLACK
    TEXT_ON_ERROR: str = BLACK
    TEXT_ON_SUCCESS: str = BLACK

    # Border colors
    BORDER: str = "#424242"
    BORDER_LIGHT: str = "#303030"
    BORDER_FOCUS: str = "#90CAF9"  # PRIMARY
    BORDER_ERROR: str = "#E57373"  # ERROR

    # PFMEA domain-specific colors
    PFMEA_AI_GENERATED: str = "#EF5350"  # Red 400 for visibility on dark
    PFMEA_ROW_EVEN: str = "#1A2A35"  # Dark blue tint for even rows
    PFMEA_HEADER: str = "#1E1E1E"  # Dark header background

    # Table-specific colors
    TABLE_BORDER: str = "#424242"
    TABLE_HEADER_BG: str = "#1E1E1E"
    TABLE_ROW_EVEN: str = "#1A1A1A"
    TABLE_CONTAINER_BORDER: str = "#303030"

    def to_css_variables(self) -> str:
        """Generate CSS custom properties from dark color tokens.

        Returns:
            CSS string with :root variables for dark theme.
        """
        lines = ["[data-theme='dark'] {"]
        for attr in dir(self):
            if attr.isupper() and not attr.startswith("_"):
                value = getattr(self, attr)
                if isinstance(value, str) and value.startswith("#"):
                    css_name = attr.lower().replace("_", "-")
                    lines.append(f"  --pfmea-{css_name}: {value};")
        lines.append("}")
        return "\n".join(lines)


__all__ = ["Colors", "DarkColors"]
