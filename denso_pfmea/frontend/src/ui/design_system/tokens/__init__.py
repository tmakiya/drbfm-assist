"""Design tokens for PFMEA UI.

Centralized definitions for colors, typography, spacing, and shadows.
These tokens ensure consistent styling across the application.
"""

from __future__ import annotations

from .colors import Colors, DarkColors
from .shadows import BorderRadius, Shadows, Transitions
from .spacing import Spacing
from .typography import Typography

# Singleton instances for direct import
colors = Colors()
dark_colors = DarkColors()
spacing = Spacing()
typography = Typography()
shadows = Shadows()
border_radius = BorderRadius()
transitions = Transitions()

__all__ = [
    "colors",
    "dark_colors",
    "spacing",
    "typography",
    "shadows",
    "border_radius",
    "transitions",
    "Colors",
    "DarkColors",
    "Spacing",
    "Typography",
    "Shadows",
    "BorderRadius",
    "Transitions",
]
