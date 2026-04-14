"""Typography tokens for PFMEA UI design system.

This module defines font families, sizes, weights, and line heights
for consistent typography across the application.

Usage:
    from src.ui.design_system.tokens import typography

    font_family = typography.FONT_FAMILY_PRIMARY
    heading_style = typography.HEADING_1
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FontSpec:
    """Specification for a text style.

    Combines font family, size, weight, and line height into a single
    reusable definition.
    """

    family: str
    size: str
    weight: str | int
    line_height: str

    def to_css(self) -> str:
        """Generate CSS properties for this font specification.

        Returns:
            CSS string with font properties.
        """
        return (
            f"font-family: {self.family}; "
            f"font-size: {self.size}; "
            f"font-weight: {self.weight}; "
            f"line-height: {self.line_height};"
        )


class Typography:
    """Design system typography tokens.

    Provides consistent font specifications for all text styles
    used in the application.
    """

    # Font families
    FONT_FAMILY_PRIMARY: str = (
        '"BIZ UDPゴシック", "Noto Sans JP", "Hiragino Sans", '
        '"Hiragino Kaku Gothic ProN", Meiryo, sans-serif'
    )
    FONT_FAMILY_MONO: str = (
        '"Source Code Pro", "Consolas", "Monaco", "Andale Mono", monospace'
    )

    # Font sizes (rem units for accessibility)
    SIZE_XS: str = "0.75rem"  # 12px
    SIZE_SM: str = "0.875rem"  # 14px
    SIZE_MD: str = "1rem"  # 16px (base)
    SIZE_LG: str = "1.125rem"  # 18px
    SIZE_XL: str = "1.25rem"  # 20px
    SIZE_2XL: str = "1.5rem"  # 24px
    SIZE_3XL: str = "1.875rem"  # 30px
    SIZE_4XL: str = "2.25rem"  # 36px

    # Pixel equivalents for specific use cases (e.g., tables)
    SIZE_PX_11: str = "11px"
    SIZE_PX_12: str = "12px"
    SIZE_PX_13: str = "13px"
    SIZE_PX_14: str = "14px"
    SIZE_PX_16: str = "16px"

    # Font weights
    WEIGHT_THIN: int = 100
    WEIGHT_LIGHT: int = 300
    WEIGHT_NORMAL: int = 400
    WEIGHT_MEDIUM: int = 500
    WEIGHT_SEMIBOLD: int = 600
    WEIGHT_BOLD: int = 700
    WEIGHT_EXTRABOLD: int = 800

    # Line heights
    LINE_HEIGHT_NONE: str = "1"
    LINE_HEIGHT_TIGHT: str = "1.25"
    LINE_HEIGHT_SNUG: str = "1.375"
    LINE_HEIGHT_NORMAL: str = "1.5"
    LINE_HEIGHT_RELAXED: str = "1.625"
    LINE_HEIGHT_LOOSE: str = "2"

    # Letter spacing
    LETTER_SPACING_TIGHTER: str = "-0.05em"
    LETTER_SPACING_TIGHT: str = "-0.025em"
    LETTER_SPACING_NORMAL: str = "0"
    LETTER_SPACING_WIDE: str = "0.025em"
    LETTER_SPACING_WIDER: str = "0.05em"

    # Predefined text styles - Headings
    HEADING_1: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_3XL,
        weight=WEIGHT_BOLD,
        line_height=LINE_HEIGHT_TIGHT,
    )

    HEADING_2: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_2XL,
        weight=WEIGHT_SEMIBOLD,
        line_height=LINE_HEIGHT_TIGHT,
    )

    HEADING_3: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_XL,
        weight=WEIGHT_SEMIBOLD,
        line_height=LINE_HEIGHT_SNUG,
    )

    HEADING_4: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_LG,
        weight=WEIGHT_SEMIBOLD,
        line_height=LINE_HEIGHT_SNUG,
    )

    # Predefined text styles - Body text
    BODY: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_MD,
        weight=WEIGHT_NORMAL,
        line_height=LINE_HEIGHT_NORMAL,
    )

    BODY_SMALL: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_SM,
        weight=WEIGHT_NORMAL,
        line_height=LINE_HEIGHT_NORMAL,
    )

    BODY_LARGE: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_LG,
        weight=WEIGHT_NORMAL,
        line_height=LINE_HEIGHT_RELAXED,
    )

    # Predefined text styles - Special
    CAPTION: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_XS,
        weight=WEIGHT_NORMAL,
        line_height=LINE_HEIGHT_NORMAL,
    )

    LABEL: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_SM,
        weight=WEIGHT_MEDIUM,
        line_height=LINE_HEIGHT_NORMAL,
    )

    CODE: FontSpec = FontSpec(
        family=FONT_FAMILY_MONO,
        size=SIZE_SM,
        weight=WEIGHT_NORMAL,
        line_height=LINE_HEIGHT_RELAXED,
    )

    # Table-specific styles
    TABLE_HEADER: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_PX_13,
        weight=WEIGHT_SEMIBOLD,
        line_height=LINE_HEIGHT_TIGHT,
    )

    TABLE_CELL: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_PX_13,
        weight=WEIGHT_NORMAL,
        line_height=LINE_HEIGHT_NORMAL,
    )

    # Button styles
    BUTTON: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_SM,
        weight=WEIGHT_MEDIUM,
        line_height=LINE_HEIGHT_TIGHT,
    )

    BUTTON_SMALL: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_XS,
        weight=WEIGHT_MEDIUM,
        line_height=LINE_HEIGHT_TIGHT,
    )

    BUTTON_LARGE: FontSpec = FontSpec(
        family=FONT_FAMILY_PRIMARY,
        size=SIZE_MD,
        weight=WEIGHT_MEDIUM,
        line_height=LINE_HEIGHT_TIGHT,
    )

    def to_css_variables(self) -> str:
        """Generate CSS custom properties from typography tokens.

        Returns:
            CSS string with :root variables for typography.
        """
        lines = [":root {"]
        lines.append(f"  --pfmea-font-family-primary: {self.FONT_FAMILY_PRIMARY};")
        lines.append(f"  --pfmea-font-family-mono: {self.FONT_FAMILY_MONO};")
        lines.append("")
        lines.append("  /* Font sizes */")
        for attr in ["SIZE_XS", "SIZE_SM", "SIZE_MD", "SIZE_LG", "SIZE_XL", "SIZE_2XL"]:
            value = getattr(self, attr)
            css_name = attr.lower().replace("_", "-")
            lines.append(f"  --pfmea-font-{css_name}: {value};")
        lines.append("")
        lines.append("  /* Font weights */")
        for attr in [
            "WEIGHT_NORMAL",
            "WEIGHT_MEDIUM",
            "WEIGHT_SEMIBOLD",
            "WEIGHT_BOLD",
        ]:
            value = getattr(self, attr)
            css_name = attr.lower().replace("_", "-")
            lines.append(f"  --pfmea-font-{css_name}: {value};")
        lines.append("")
        lines.append("  /* Line heights */")
        for attr in [
            "LINE_HEIGHT_TIGHT",
            "LINE_HEIGHT_NORMAL",
            "LINE_HEIGHT_RELAXED",
        ]:
            value = getattr(self, attr)
            css_name = attr.lower().replace("_", "-")
            lines.append(f"  --pfmea-{css_name}: {value};")
        lines.append("}")
        return "\n".join(lines)


__all__ = ["Typography", "FontSpec"]
