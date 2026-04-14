from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any


@dataclass
class DatasetStore:
    storage: MutableMapping[str, Any]
    signature_key: str = "dataset_signature"

    def mark_if_changed(self, signature: str) -> bool:
        current = self.storage.get(self.signature_key)
        if current == signature:
            return False
        self.storage[self.signature_key] = signature
        return True

    def clear(self) -> None:
        self.storage.pop(self.signature_key, None)

    def get(self) -> str | None:
        value = self.storage.get(self.signature_key)
        if value is None:
            return None
        return str(value)


@dataclass
class AnalysisStore:
    storage: MutableMapping[str, Any]
    result_key: str = "analysis_result"
    selection_key: str = "analysis_selection"
    status_key: str = "analysis_status"

    def clear(self) -> None:
        self.storage.pop(self.result_key, None)
        self.storage.pop(self.status_key, None)
        self.storage.pop(self.selection_key, None)

    def clear_status(self) -> None:
        self.storage.pop(self.status_key, None)

    def result(self) -> Any | None:
        return self.storage.get(self.result_key)

    def set_result(self, result: Any) -> None:
        self.storage[self.result_key] = result

    def selection(self) -> tuple[str, str] | None:
        value = self.storage.get(self.selection_key)
        if isinstance(value, tuple) and len(value) == 2:
            return str(value[0]), str(value[1])
        return None

    def set_selection(self, selection: tuple[str, str]) -> None:
        self.storage[self.selection_key] = tuple(selection)

    def status(self) -> dict[str, Any] | None:
        status = self.storage.get(self.status_key)
        if not isinstance(status, dict):
            return None
        if "label" not in status or "value" not in status or "kind" not in status:
            return None
        payload: dict[str, Any] = {
            "label": str(status["label"]),
            "value": int(status["value"]),
            "kind": str(status["kind"]),
        }
        details = status.get("details")
        if isinstance(details, dict):
            payload["details"] = details
        return payload

    def set_status(
        self,
        *,
        label: str,
        value: int,
        kind: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        stored: dict[str, Any] = {
            "label": label,
            "value": int(value),
            "kind": str(kind),
        }
        if details is not None:
            stored["details"] = dict(details)
        self.storage[self.status_key] = stored


@dataclass
class ThemeStore:
    """Encapsulates all theme-related session state access."""

    storage: MutableMapping[str, Any]
    base_key: str = "theme_base"
    detection_state_key: str = "theme_detection_state"
    configured_key: str = "theme_configured"
    applied_base_key: str = "theme_applied_base"
    detection_attempts_key: str = "theme_detection_attempts"

    def get_base(self) -> str:
        """Get current theme base, defaulting to 'light'."""
        value = self.storage.get(self.base_key)
        if value is None:
            return "light"
        normalized = str(value).strip().lower()
        if normalized in ("light", "dark"):
            return normalized
        return "light"

    def set_base(self, theme: str) -> None:
        """Set theme base ('light' or 'dark')."""
        normalized = str(theme).strip().lower()
        if normalized not in ("light", "dark"):
            raise ValueError(f"Invalid theme: {theme}")
        self.storage[self.base_key] = normalized

    def get_detection_state(self) -> str:
        """Get detection state machine state."""
        value = self.storage.get(self.detection_state_key)
        if value is None:
            return "pending"
        state = str(value)
        if state in ("pending", "active", "done", "failed"):
            return state
        return "pending"

    def set_detection_state(self, state: str) -> None:
        """Set detection state ('pending', 'active', 'done', 'failed')."""
        if state not in ("pending", "active", "done", "failed"):
            raise ValueError(f"Invalid detection state: {state}")
        self.storage[self.detection_state_key] = state

    def is_configured(self) -> bool:
        """Check if theme has been configured."""
        return bool(self.storage.get(self.configured_key, False))

    def set_configured(self, configured: bool) -> None:
        """Mark theme as configured or not."""
        self.storage[self.configured_key] = bool(configured)

    def get_applied_base(self) -> str | None:
        """Get the last applied base theme."""
        value = self.storage.get(self.applied_base_key)
        if value is None:
            return None
        return str(value)

    def set_applied_base(self, theme: str) -> None:
        """Set the last applied base theme."""
        self.storage[self.applied_base_key] = str(theme)

    def get_detection_attempts(self) -> int:
        """Get number of detection attempts."""
        value = self.storage.get(self.detection_attempts_key, 0)
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def increment_detection_attempts(self) -> int:
        """Increment and return detection attempts."""
        attempts = self.get_detection_attempts() + 1
        self.storage[self.detection_attempts_key] = attempts
        return attempts

    def reset_detection(self) -> None:
        """Reset detection state and attempts."""
        self.storage.pop(self.detection_state_key, None)
        self.storage.pop(self.detection_attempts_key, None)

    def clear(self) -> None:
        """Clear all theme-related state."""
        self.storage.pop(self.base_key, None)
        self.storage.pop(self.detection_state_key, None)
        self.storage.pop(self.configured_key, None)
        self.storage.pop(self.applied_base_key, None)
        self.storage.pop(self.detection_attempts_key, None)


__all__ = [
    "AnalysisStore",
    "DatasetStore",
    "ThemeStore",
]
