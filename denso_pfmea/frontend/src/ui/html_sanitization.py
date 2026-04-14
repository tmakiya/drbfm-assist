"""HTMLサニタイズユーティリティ。

正規表現を自前で維持する代わりに `bleach` を利用して、安全な最小構成で
テキスト／HTMLをクリーンアップする。
"""

from __future__ import annotations

import html
import re
from typing import Any, Iterable

import bleach
import pandas as pd

_ALLOWED_TAGS: Iterable[str] = (
    "a",
    "b",
    "br",
    "code",
    "div",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
)
_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
}
_ALLOWED_PROTOCOLS = set(bleach.sanitizer.ALLOWED_PROTOCOLS) | {"data"}
_SCRIPT_STYLE_RE = re.compile(
    r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_dangerous_blocks(text: str) -> str:
    return _SCRIPT_STYLE_RE.sub("", text)


def _clean_html(html_string: str | Any) -> str:
    text = "" if html_string is None else str(html_string)
    text = _strip_dangerous_blocks(text)
    return bleach.clean(
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )


def escape_html(text: str | Any) -> str:
    """テキストをHTML用にサニタイズして返す。"""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def sanitize_dataframe_for_html(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame内の文字列列を一括でサニタイズする。"""
    if df.empty:
        return df.copy()
    sanitized = df.copy()
    for col in sanitized.select_dtypes(include=["object"]).columns:
        sanitized[col] = sanitized[col].apply(escape_html)
    return sanitized


def sanitize_html_attributes(html_string: str) -> str:
    """HTML属性を含む文字列をホワイトリスト方式でサニタイズする。"""
    return _clean_html(html_string)


def sanitize_style_tag(html_string: str) -> str:
    """`bleach` を用いたサニタイズと同義。互換性維持のためのラッパー。"""
    return _clean_html(html_string)


def fully_sanitize_html(html_string: str) -> str:
    """Streamlit描画に渡すHTML断片の最終サニタイズ処理。"""
    return _clean_html(html_string)


__all__ = [
    "escape_html",
    "sanitize_dataframe_for_html",
    "sanitize_html_attributes",
    "sanitize_style_tag",
    "fully_sanitize_html",
]
