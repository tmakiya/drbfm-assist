"""Project-wide path helpers."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
TEST_DATA_DIR = PROJECT_ROOT / "test_data"
PFMEA_SAMPLE_DIR = TEST_DATA_DIR / "pfmea"
BOP_SAMPLE_DIR = TEST_DATA_DIR / "bop"

__all__ = [
    "ANALYSIS_DIR",
    "BOP_SAMPLE_DIR",
    "DOCS_DIR",
    "PFMEA_SAMPLE_DIR",
    "PROJECT_ROOT",
    "TEST_DATA_DIR",
]
