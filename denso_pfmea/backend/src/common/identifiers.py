from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_NON_WORD_PATTERN = re.compile(r"[^0-9a-z]+")
_SLUG_SEPARATOR = "-"
_MAX_SLUG_LENGTH = 96
_HASH_PREFIX = "chg"
_HASH_LENGTH = 12


def _normalize_component(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.strip().lower()
    normalized = _NON_WORD_PATTERN.sub(_SLUG_SEPARATOR, normalized)
    normalized = normalized.strip(_SLUG_SEPARATOR)
    return normalized


def _compose_slug(components: Iterable[str]) -> str:
    slug = _SLUG_SEPARATOR.join(
        filter(None, (_normalize_component(component) for component in components))
    )
    if len(slug) > _MAX_SLUG_LENGTH:
        slug = slug[:_MAX_SLUG_LENGTH].rstrip(_SLUG_SEPARATOR)
    return slug or "item"


def _short_hash(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"{_HASH_PREFIX}_{digest[:_HASH_LENGTH]}"


def generate_change_id(*components: str | None) -> str:
    """Generate a deterministic, slugified change identifier.

    Components are normalized (NFKC, lower-case, non-word characters replaced with '-')
    and joined with '-' to produce a human-friendly slug. To guarantee stability and uniqueness,
    a short hash is appended.
    """

    slug = _compose_slug(c for c in components if c is not None)
    hashed = _short_hash(slug)
    return f"{slug}__{hashed}"


__all__ = ["generate_change_id"]
