from __future__ import annotations

from src.common.config import BopConfig, load_bop_config

_BOP_CONFIG: BopConfig | None = None


def get_bop_config() -> BopConfig:
    global _BOP_CONFIG
    if _BOP_CONFIG is None:
        _BOP_CONFIG = load_bop_config()
    return _BOP_CONFIG


__all__ = ["get_bop_config"]
