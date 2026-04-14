from __future__ import annotations

import threading
from types import ModuleType
from typing import Any

from src.common.concurrency import (
    get_streamlit_task_wrapper as _get_streamlit_task_wrapper,
)

_BOP_MODULE: ModuleType | None = None
_PFMEA_MODULE: ModuleType | None = None
_VALIDATION_MODULE: ModuleType | None = None
_VERTEX_MODULES: dict[str, Any] | None = None
_VERTEX_AVAILABLE: bool | None = None

# Thread-safe module loading lock (prevents TOCTOU race conditions)
_MODULE_LOADER_LOCK = threading.Lock()


def get_bop_module() -> ModuleType:
    """Get BOP module (thread-safe lazy loading)."""
    global _BOP_MODULE
    with _MODULE_LOADER_LOCK:
        if _BOP_MODULE is None:
            from src.common import bop as bop_module

            _BOP_MODULE = bop_module
        return _BOP_MODULE


def get_pfmea_module() -> ModuleType:
    """Get PFMEA module (thread-safe lazy loading)."""
    global _PFMEA_MODULE
    with _MODULE_LOADER_LOCK:
        if _PFMEA_MODULE is None:
            from src.common import pfmea as pfmea_module

            _PFMEA_MODULE = pfmea_module
        return _PFMEA_MODULE


def get_validation_module() -> ModuleType:
    """Get validation module (thread-safe lazy loading)."""
    global _VALIDATION_MODULE
    with _MODULE_LOADER_LOCK:
        if _VALIDATION_MODULE is None:
            from src.common import validation as validation_module

            _VALIDATION_MODULE = validation_module
        return _VALIDATION_MODULE


def ensure_vertex_modules() -> tuple[bool, dict[str, Any] | None]:
    """Ensure Vertex AI modules are loaded (thread-safe)."""
    global _VERTEX_AVAILABLE, _VERTEX_MODULES
    with _MODULE_LOADER_LOCK:
        if _VERTEX_AVAILABLE is not None:
            return _VERTEX_AVAILABLE, _VERTEX_MODULES
        try:  # pragma: no cover - Google Gen AI SDK未導入環境向け
            from google import genai
            from google.oauth2 import service_account

            _VERTEX_AVAILABLE = True
            _VERTEX_MODULES = {"genai": genai, "service_account": service_account}
        except ImportError:
            _VERTEX_AVAILABLE = False
            _VERTEX_MODULES = None
        return _VERTEX_AVAILABLE, _VERTEX_MODULES


get_streamlit_task_wrapper = _get_streamlit_task_wrapper


__all__ = [
    "ensure_vertex_modules",
    "get_bop_module",
    "get_pfmea_module",
    "get_streamlit_task_wrapper",
    "get_validation_module",
]
