"""Cache coordination utilities for PFMEA mapping runtime."""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any

logger = logging.getLogger(__name__)


class MappingCacheCoordinator:
    """Manages session cache for PFMEA mapping.

    Note: Persistent cache (SQLite) has been removed to avoid storing
    confidential customer data on disk.
    """

    def __init__(self, session_manager: Any) -> None:
        self._session_cache: MutableMapping[str, Mapping[str, Any]] = {}
        self._cache_updater = getattr(
            session_manager, "update_pfmea_mapping_cache", None
        )
        self._results_setter = getattr(
            session_manager, "set_pfmea_mapping_results", None
        )
        self._log_setter = getattr(session_manager, "set_pfmea_mapping_logs", None)

        cache_getter = getattr(session_manager, "get_pfmea_mapping_cache", None)
        if cache_getter is not None:
            cache = cache_getter()
            if isinstance(cache, MutableMapping):
                self._session_cache = cache

        # Persistent cache disabled for security reasons
        self._persistent_cache = None

    # Session helpers ---------------------------------------------------------
    @property
    def session_cache(self) -> MutableMapping[str, Mapping[str, Any]]:
        return self._session_cache

    @property
    def persistent_cache(self) -> None:
        """Persistent cache is disabled for security reasons."""
        return None

    def fetch(self, signature: str) -> tuple[Mapping[str, Any] | None, str | None]:
        """Return cached payload and source label.

        Only session cache is used. Persistent cache is disabled.
        """
        entry = self._session_cache.get(signature)
        if entry:
            return dict(entry), "session"
        return None, None

    def store_results(self, payload: Mapping[str, Any]) -> None:
        if self._results_setter is not None:
            self._results_setter(payload)

    def store_logs(self, dataframe: Any) -> None:  # pragma: no cover - Streamlit path
        if self._log_setter is not None:
            self._log_setter(dataframe)

    def update_caches(self, signature: str, payload: Mapping[str, Any]) -> None:
        """Update session cache only. Persistent cache is disabled."""
        if self._cache_updater is not None:
            self._cache_updater(signature, payload)
        else:
            self._session_cache[str(signature)] = dict(payload)

    def close(self) -> None:
        """No-op since persistent cache is disabled."""
        pass


__all__ = ["MappingCacheCoordinator"]
