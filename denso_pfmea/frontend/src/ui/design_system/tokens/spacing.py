"""Spacing tokens for PFMEA UI design system.

This module defines spacing values based on an 8px grid system
for consistent layout and component spacing.

Usage:
    from src.ui.design_system.tokens import spacing

    margin = spacing.MD  # "16px"
    padding = spacing.scale(1.5)  # "12px"
"""

from __future__ import annotations


class Spacing:
    """Design system spacing tokens based on 8px grid.

    All spacing values are derived from a base unit of 8px to ensure
    consistent rhythm and alignment across the application.
    """

    # Base unit (8px)
    UNIT: int = 8

    # Spacing scale
    NONE: str = "0"
    PX_1: str = "1px"  # Border width
    PX_2: str = "2px"  # Small border/outline
    XS: str = "4px"  # 0.5 unit - icon/text gap
    SM: str = "8px"  # 1 unit - related elements
    MD: str = "16px"  # 2 units - component groups
    LG: str = "24px"  # 3 units - section spacing
    XL: str = "32px"  # 4 units - major sections
    XXL: str = "48px"  # 6 units - page structure
    XXXL: str = "64px"  # 8 units - large gaps

    # Negative spacing (for margin collapse, etc.)
    NEG_XS: str = "-4px"
    NEG_SM: str = "-8px"
    NEG_MD: str = "-16px"

    # Component-specific spacing
    # Buttons
    BUTTON_PADDING_X: str = MD  # Horizontal padding
    BUTTON_PADDING_Y: str = SM  # Vertical padding
    BUTTON_GAP: str = SM  # Gap between button elements

    # Cards
    CARD_PADDING: str = MD
    CARD_PADDING_COMPACT: str = SM
    CARD_GAP: str = MD

    # Tables
    TABLE_CELL_PADDING: str = f"{SM} {MD}"  # 8px 16px for readability
    TABLE_CELL_PADDING_X: str = MD
    TABLE_CELL_PADDING_Y: str = SM
    TABLE_ROW_GAP: str = NONE

    # Inputs
    INPUT_PADDING_X: str = SM
    INPUT_PADDING_Y: str = SM
    INPUT_GAP: str = SM  # Between label and input

    # Forms
    FORM_FIELD_GAP: str = MD  # Between form fields
    FORM_SECTION_GAP: str = LG  # Between form sections
    FORM_LABEL_GAP: str = XS  # Between label and input

    # Layout spacing
    PAGE_PADDING: str = LG
    PAGE_PADDING_MOBILE: str = MD
    SECTION_GAP: str = XL
    SECTION_GAP_COMPACT: str = LG
    COMPONENT_GAP: str = MD
    INLINE_GAP: str = SM

    # Sidebar
    SIDEBAR_PADDING: str = MD
    SIDEBAR_ITEM_GAP: str = SM

    # Header
    HEADER_PADDING: str = MD
    HEADER_HEIGHT: str = "64px"

    # Modal/Dialog
    MODAL_PADDING: str = LG
    MODAL_HEADER_GAP: str = MD
    MODAL_FOOTER_GAP: str = MD

    # Progress panel
    PROGRESS_PADDING: str = MD
    PROGRESS_GAP: str = SM

    # Toast/Alert
    ALERT_PADDING: str = MD
    ALERT_ICON_GAP: str = SM

    @classmethod
    def scale(cls, multiplier: float) -> str:
        """Generate spacing value by multiplier of base unit.

        Args:
            multiplier: Number to multiply with base unit (8px).

        Returns:
            Spacing value as CSS pixel string.

        Example:
            >>> Spacing.scale(0.5)  # "4px"
            >>> Spacing.scale(1.5)  # "12px"
            >>> Spacing.scale(3)    # "24px"
        """
        return f"{int(cls.UNIT * multiplier)}px"

    @classmethod
    def rem(cls, value: float) -> str:
        """Generate spacing value in rem units.

        Args:
            value: Number of rem units.

        Returns:
            Spacing value as CSS rem string.

        Example:
            >>> Spacing.rem(1)    # "1rem"
            >>> Spacing.rem(0.5)  # "0.5rem"
        """
        return f"{value}rem"

    def to_css_variables(self) -> str:
        """Generate CSS custom properties from spacing tokens.

        Returns:
            CSS string with :root variables for spacing.
        """
        lines = [":root {"]
        lines.append(f"  --pfmea-spacing-unit: {self.UNIT}px;")
        lines.append("")
        lines.append("  /* Spacing scale */")
        for attr in ["NONE", "XS", "SM", "MD", "LG", "XL", "XXL", "XXXL"]:
            value = getattr(self, attr)
            css_name = attr.lower()
            lines.append(f"  --pfmea-spacing-{css_name}: {value};")
        lines.append("")
        lines.append("  /* Component spacing */")
        lines.append(f"  --pfmea-table-cell-padding: {self.TABLE_CELL_PADDING};")
        lines.append(f"  --pfmea-card-padding: {self.CARD_PADDING};")
        lines.append(f"  --pfmea-input-padding-x: {self.INPUT_PADDING_X};")
        lines.append(f"  --pfmea-input-padding-y: {self.INPUT_PADDING_Y};")
        lines.append("")
        lines.append("  /* Layout spacing */")
        lines.append(f"  --pfmea-page-padding: {self.PAGE_PADDING};")
        lines.append(f"  --pfmea-section-gap: {self.SECTION_GAP};")
        lines.append(f"  --pfmea-component-gap: {self.COMPONENT_GAP};")
        lines.append("}")
        return "\n".join(lines)


__all__ = ["Spacing"]
