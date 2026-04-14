"""Text normalization utilities for cause part processing."""

import re
import unicodedata
from typing import Dict, List

import pandas as pd


def basic_normalize_text(text):
    """Normalize text with full-width/half-width conversion and space cleanup."""
    if pd.isna(text) or text == "":
        return text

    # Convert full-width alphanumeric and symbols to half-width
    # This keeps katakana and hiragana in full-width
    normalized = unicodedata.normalize("NFKC", text)

    # Convert English letters to lowercase
    normalized = "".join(char.lower() if char.isascii() and char.isalpha() else char for char in normalized)

    # Remove unnecessary spaces at beginning and end
    normalized = normalized.strip()

    # Remove multiple consecutive spaces
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized


def build_longest_subber(correction_dict: Dict[str, List[str]]):
    """Build a substitution function that replaces notation variations with canonical forms.

    Args:
        correction_dict: Dictionary mapping canonical forms to lists of variations

    Returns:
        Function that performs substitutions on input text

    """
    # Flatten canonical->variants to variant->canonical (exclude no-ops)
    v2c = {}
    for can, vars in correction_dict.items():
        for v in vars:
            if v and v != can:
                v2c[v] = can

    # Sort variants by length in descending order (escape regex meta characters)
    variants = sorted(v2c.keys(), key=len, reverse=True)
    escaped = [re.escape(v) for v in variants]

    ascii_mask = re.compile(r"^[a-z0-9/_+\-]+$")
    ascii_alts = [e for v, e in zip(variants, escaped) if ascii_mask.match(v)]
    other_alts = [e for v, e in zip(variants, escaped) if not ascii_mask.match(v)]

    # Alternation (non-ASCII first, then ASCII with word boundaries; both ordered by length)
    parts = []
    if other_alts:
        parts.append("(?:%s)" % "|".join(other_alts))
    if ascii_alts:
        # Ensure ASCII tokens are not surrounded by alphanumeric/underscore/plus/minus/slash characters
        parts.append(r"(?<![A-Za-z0-9/_+\-])(?:%s)(?![A-Za-z0-9/_+\-])" % "|".join(ascii_alts))

    if not parts:
        return lambda s: s  # No substitutions

    rx = re.compile("|".join(parts))

    def repl(m):
        s = m.group(0)
        # Input is expected to be ASCII lowercase. Check lower() as fallback just in case
        return v2c.get(s, v2c.get(s.lower(), s))

    def sub(text: str) -> str:
        return rx.sub(repl, text)

    return sub
