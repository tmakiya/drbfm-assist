"""Service-level helpers for change analysis and LLM連携。"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["change_analysis", "llm_gateway", "llm_workflow", "pfmea_ai"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
