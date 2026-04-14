"""Type-safe session state keys for Streamlit application.

This module provides a centralized enum for all session state keys,
preventing typos and improving maintainability.
"""

from __future__ import annotations

from enum import StrEnum


class SessionKeys(StrEnum):
    """Enum for all session state keys used throughout the application.

    Using StrEnum ensures type safety and prevents typos when accessing
    session state. All session state access should use these keys.

    Example:
        >>> st.session_state[SessionKeys.DATASET_SIGNATURE] = "abc123"
        >>> signature = st.session_state[SessionKeys.DATASET_SIGNATURE]
    """

    # Dataset management
    DATASET_SIGNATURE = "dataset_signature"

    # LLM state
    LLM_STRUCTURED_ROWS = "llm_structured_rows"
    LLM_METRICS = "llm_metrics"
    LLM_REQUEST = "llm_requested"
    LLM_WORKFLOW_INFO = "llm_workflow_info"

    # Vertex AI model configuration
    VERTEX_MODELS = "vertex_models"
    VERTEX_MODEL_INFO = "vertex_model_info"
    VERTEX_MODEL_CURRENT = "vertex_model_current"
    VERTEX_MODEL_PREFERENCE = "vertex_model_preference"

    # PFMEA mapping
    PFMEA_MAPPING_CACHE = "pfmea_function_mapping_cache"
    PFMEA_MAPPING_RESULTS = "pfmea_function_mapping_results"
    PFMEA_MAPPING_READY = "pfmea_function_mapping_ready"
    PFMEA_SIGNATURE = "pfmea_signature"

    # Analysis state
    ANALYSIS_RESULT = "analysis_result"
    ANALYSIS_SELECTION = "analysis_selection"
    ANALYSIS_STATUS = "analysis_status"
    ANALYSIS_RUNNING = "analysis_running"
    ANALYSIS_REQUEST = "analysis_requested"

    # Comparison mode
    COMPARISON_MODE = "comparison_mode"

    # Theme management
    THEME_BASE = "theme_base"
    THEME_DETECTION_STATE = "theme_detection_state"
    THEME_CONFIGURED = "theme_configured"
    THEME_APPLIED_BASE = "theme_applied_base"
    THEME_DETECTION_ATTEMPTS = "theme_detection_attempts"


# Widget keys (not stored in session state, but used for widget identification)
class WidgetKeys(StrEnum):
    """Enum for widget keys used in Streamlit components.

    These keys identify widgets and should be unique across the application.
    """

    # File uploaders
    SOURCE_FILE_UPLOADER = "sidebar_source_bop_uploader"
    TARGET_FILE_UPLOADER = "sidebar_target_bop_uploader"
    PFMEA_FILE_UPLOADER = "sidebar_pfmea_uploader"

    # Selectors and inputs
    LLM_MODE_SELECTOR = "llm_mode_selector"
    COMPARISON_MODE_SELECTOR = "comparison_mode_selector"
    VARIANT_SOURCE_SELECT = "variant_source_select"

    # Buttons
    LLM_TRIGGER_BUTTON = "llm_trigger_button"
    ANALYSIS_TRIGGER_BUTTON = "analysis_trigger_button"


__all__ = ["SessionKeys", "WidgetKeys"]
