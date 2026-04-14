"""Common text utility helpers shared across BOP/PFMEA modules."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Literal

import pandas as pd


def sanitize(value: Any) -> str:
    """Normalize a cell value into a trimmed single-line string."""
    if value is None:
        return ""
    if isinstance(value, pd.Series):
        value = value.iloc[0]
        return sanitize(value)
    if isinstance(value, float) and math.isnan(value):
        return ""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text.replace("\n", " ")


def normalize_text(
    value: str,
    *,
    unicode_form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFKC",
    collapse_spaces: bool = True,
) -> str:
    """Normalize text with Unicode normalization and whitespace handling.

    Performs NFKC normalization (full-width to half-width, variant unification)
    and collapses consecutive whitespace characters.

    Args:
        value: Input text to normalize.
        unicode_form: Unicode normalization form (default: NFKC).
        collapse_spaces: If True, collapse consecutive spaces to single space.

    Returns:
        Normalized text with leading/trailing whitespace removed.

    Examples:
        >>> normalize_text("ボルト　Ｍ６")
        'ボルト M6'
        >>> normalize_text("　パッキン\\u3000")
        'パッキン'
        >>> normalize_text("ABC  DEF")
        'ABC DEF'
    """
    if not value:
        return ""

    # Unicode normalization (full-width -> half-width, variant unification)
    text = unicodedata.normalize(unicode_form, value)

    # Convert full-width space to half-width (fallback if NFKC doesn't convert)
    text = text.replace("\u3000", " ")

    # Collapse consecutive whitespace
    if collapse_spaces:
        text = re.sub(r"\s+", " ", text)

    # Strip leading/trailing whitespace
    return text.strip()
