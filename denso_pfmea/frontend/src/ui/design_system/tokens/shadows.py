"""Shadow, border radius, and transition tokens for PFMEA UI design system.

This module defines visual effects including box shadows, border radii,
and animation transitions for consistent component styling.

Usage:
    from src.ui.design_system.tokens import shadows, border_radius, transitions

    shadow = shadows.MD
    radius = border_radius.MD
    transition = transitions.DEFAULT
"""

from __future__ import annotations


class Shadows:
    """Design system shadow tokens.

    Provides consistent elevation and depth through shadow definitions.
    Shadows follow Material Design elevation principles.
    """

    # No shadow
    NONE: str = "none"

    # Shadow scale (increasing elevation)
    XS: str = "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
    SM: str = "0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)"
    MD: str = "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1)"
    LG: str = "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)"
    XL: str = "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)"
    XXL: str = "0 25px 50px -12px rgba(0, 0, 0, 0.25)"

    # Inner shadows
    INNER: str = "inset 0 2px 4px 0 rgba(0, 0, 0, 0.05)"
    INNER_MD: str = "inset 0 4px 6px 0 rgba(0, 0, 0, 0.1)"

    # Focus shadows (for accessibility)
    FOCUS: str = "0 0 0 3px rgba(25, 118, 210, 0.3)"  # Primary color with alpha
    FOCUS_ERROR: str = "0 0 0 3px rgba(198, 40, 40, 0.3)"  # Error color with alpha
    FOCUS_SUCCESS: str = "0 0 0 3px rgba(46, 125, 50, 0.3)"  # Success color with alpha

    # Component-specific shadows
    BUTTON_HOVER: str = MD
    CARD: str = MD
    CARD_HOVER: str = LG
    DROPDOWN: str = LG
    MODAL: str = XL
    TOOLTIP: str = MD
    SIDEBAR: str = LG

    # Dark mode shadows (increased opacity for visibility)
    DARK_SM: str = "0 1px 3px 0 rgba(0, 0, 0, 0.25), 0 1px 2px -1px rgba(0, 0, 0, 0.25)"
    DARK_MD: str = (
        "0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.3)"
    )
    DARK_LG: str = (
        "0 10px 15px -3px rgba(0, 0, 0, 0.35), 0 4px 6px -4px rgba(0, 0, 0, 0.35)"
    )


class BorderRadius:
    """Design system border radius tokens.

    Provides consistent corner rounding for UI elements.
    """

    # No rounding
    NONE: str = "0"

    # Border radius scale
    XS: str = "2px"
    SM: str = "4px"
    MD: str = "8px"
    LG: str = "12px"
    XL: str = "16px"
    XXL: str = "24px"

    # Special values
    FULL: str = "9999px"  # Fully rounded (pill shape)
    CIRCLE: str = "50%"  # Perfect circle

    # Component-specific radii
    BUTTON: str = SM
    BUTTON_PILL: str = FULL
    CARD: str = MD
    INPUT: str = SM
    MODAL: str = LG
    TOOLTIP: str = SM
    BADGE: str = FULL
    ALERT: str = SM
    TABLE: str = SM
    PROGRESS: str = FULL


class Transitions:
    """Design system animation/transition tokens.

    Provides consistent timing and easing for UI animations.
    """

    # Duration scale
    DURATION_INSTANT: str = "0ms"
    DURATION_FAST: str = "100ms"
    DURATION_NORMAL: str = "200ms"
    DURATION_SLOW: str = "300ms"
    DURATION_SLOWER: str = "500ms"

    # Easing functions
    EASE_LINEAR: str = "linear"
    EASE_DEFAULT: str = "cubic-bezier(0.4, 0, 0.2, 1)"  # Standard ease
    EASE_IN: str = "cubic-bezier(0.4, 0, 1, 1)"  # Accelerate
    EASE_OUT: str = "cubic-bezier(0, 0, 0.2, 1)"  # Decelerate
    EASE_IN_OUT: str = "cubic-bezier(0.4, 0, 0.2, 1)"  # Standard
    EASE_BOUNCE: str = "cubic-bezier(0.68, -0.55, 0.265, 1.55)"

    # Preset transitions
    NONE: str = "none"
    DEFAULT: str = f"all {DURATION_NORMAL} {EASE_DEFAULT}"
    FAST: str = f"all {DURATION_FAST} {EASE_DEFAULT}"
    SLOW: str = f"all {DURATION_SLOW} {EASE_DEFAULT}"

    # Property-specific transitions
    COLOR: str = f"color {DURATION_NORMAL} {EASE_DEFAULT}"
    BACKGROUND: str = f"background-color {DURATION_NORMAL} {EASE_DEFAULT}"
    BORDER: str = f"border-color {DURATION_NORMAL} {EASE_DEFAULT}"
    SHADOW: str = f"box-shadow {DURATION_NORMAL} {EASE_DEFAULT}"
    TRANSFORM: str = f"transform {DURATION_NORMAL} {EASE_OUT}"
    OPACITY: str = f"opacity {DURATION_NORMAL} {EASE_DEFAULT}"

    # Combined transitions
    BUTTON: str = (
        f"background-color {DURATION_FAST} {EASE_DEFAULT}, "
        f"box-shadow {DURATION_FAST} {EASE_DEFAULT}, "
        f"transform {DURATION_FAST} {EASE_DEFAULT}"
    )

    CARD_HOVER: str = (
        f"box-shadow {DURATION_NORMAL} {EASE_DEFAULT}, "
        f"transform {DURATION_NORMAL} {EASE_OUT}"
    )

    INPUT_FOCUS: str = (
        f"border-color {DURATION_FAST} {EASE_DEFAULT}, "
        f"box-shadow {DURATION_FAST} {EASE_DEFAULT}"
    )

    @classmethod
    def custom(
        cls,
        properties: str = "all",
        duration: str | None = None,
        easing: str | None = None,
    ) -> str:
        """Create a custom transition string.

        Args:
            properties: CSS properties to transition (default: "all").
            duration: Transition duration (default: DURATION_NORMAL).
            easing: Easing function (default: EASE_DEFAULT).

        Returns:
            CSS transition string.

        Example:
            >>> Transitions.custom("opacity, transform", "300ms", "ease-out")
            "opacity, transform 300ms ease-out"
        """
        dur = duration or cls.DURATION_NORMAL
        ease = easing or cls.EASE_DEFAULT
        return f"{properties} {dur} {ease}"


def generate_css_variables() -> str:
    """Generate all shadow/radius/transition CSS custom properties.

    Returns:
        CSS string with :root variables for visual effects.
    """
    shadows = Shadows()
    border_radius = BorderRadius()
    transitions = Transitions()

    lines = [":root {"]

    # Shadows
    lines.append("  /* Shadows */")
    for attr in ["NONE", "XS", "SM", "MD", "LG", "XL"]:
        value = getattr(shadows, attr)
        lines.append(f"  --pfmea-shadow-{attr.lower()}: {value};")
    lines.append(f"  --pfmea-shadow-focus: {shadows.FOCUS};")
    lines.append("")

    # Border radii
    lines.append("  /* Border radius */")
    for attr in ["NONE", "XS", "SM", "MD", "LG", "XL", "FULL"]:
        value = getattr(border_radius, attr)
        lines.append(f"  --pfmea-radius-{attr.lower()}: {value};")
    lines.append("")

    # Transitions
    lines.append("  /* Transitions */")
    lines.append(f"  --pfmea-transition-duration-fast: {transitions.DURATION_FAST};")
    lines.append(
        f"  --pfmea-transition-duration-normal: {transitions.DURATION_NORMAL};"
    )
    lines.append(f"  --pfmea-transition-duration-slow: {transitions.DURATION_SLOW};")
    lines.append(f"  --pfmea-transition-default: {transitions.DEFAULT};")

    lines.append("}")
    return "\n".join(lines)


__all__ = [
    "Shadows",
    "BorderRadius",
    "Transitions",
    "generate_css_variables",
]
