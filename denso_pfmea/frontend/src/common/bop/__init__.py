"""Public interface for BOP parsing and diff utilities."""

from __future__ import annotations

from src.common.config import BopConfig

from .constants import ABSENT_MARKERS
from .diff import (
    compare_bop_tables,
    detect_changes,
    extract_keywords,
    normalize_part_value,
)
from .models import BopDataset, ChangeRecord, PartColumn
from .parser import (
    _build_block_station_maps,
    _build_variant_records,
    _collect_part_columns,
    _extract_metadata_headers,
    load_bop_master,
)
from .settings import get_bop_config

__all__ = [
    "ABSENT_MARKERS",
    "BopConfig",
    "BopDataset",
    "ChangeRecord",
    "PartColumn",
    "_build_block_station_maps",
    "_build_variant_records",
    "_collect_part_columns",
    "_extract_metadata_headers",
    "compare_bop_tables",
    "detect_changes",
    "extract_keywords",
    "get_bop_config",
    "load_bop_master",
    "normalize_part_value",
]
