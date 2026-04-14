"""Modularized components for the main Streamlit page."""

from .constants import (
    DEFAULT_VERTEX_MODEL,
    DEFAULT_VERTEX_REGION,
    PRO_VERTEX_MODEL,
    PROMPT_TEMPLATE_NAME,
)
from .data_loaders import (
    build_dataset_signature,
    collect_missing_inputs,
)
from .environment import ensure_env_loaded
from .page import format_comparison_label, render_main_page, setup_page
from .validators import validate_uploaded_datasets

__all__ = [
    "DEFAULT_VERTEX_MODEL",
    "DEFAULT_VERTEX_REGION",
    "PROMPT_TEMPLATE_NAME",
    "PRO_VERTEX_MODEL",
    "build_dataset_signature",
    "collect_missing_inputs",
    "ensure_env_loaded",
    "format_comparison_label",
    "render_main_page",
    "setup_page",
    "validate_uploaded_datasets",
]
