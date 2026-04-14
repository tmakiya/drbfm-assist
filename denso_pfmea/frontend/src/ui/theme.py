"""Theme management for PFMEA UI.

This module handles browser theme detection, Streamlit page configuration,
and integration with the design system.
"""

from __future__ import annotations

import inspect
import os
from contextlib import suppress
from pathlib import Path
from textwrap import dedent
from typing import Any, Literal, cast

import streamlit as st
import streamlit.components.v1 as components
from streamlit import config as st_config

from src.ui.state.session_manager import get_session_manager

AUTO_THEME_COMPONENT_KEY = "auto_theme_detector"
AUTO_THEME_STATE_KEY = "_auto_theme_base"
AUTO_THEME_DETECTION_STATE_KEY = "_auto_theme_detection_state"
AUTO_THEME_CONFIGURED_KEY = "_auto_theme_configured"
AUTO_THEME_APPLIED_BASE_KEY = "_auto_theme_applied_base"
DEFAULT_THEME_BASE = "light"
_DETECTION_STATE_PENDING = "pending"
_DETECTION_STATE_ACTIVE = "active"
_DETECTION_STATE_DONE = "done"
_DETECTION_STATE_FAILED = "failed"
_DETECTION_MAX_ATTEMPTS = 3
_DETECTION_ATTEMPT_KEY = "_auto_theme_detection_attempts"

_THEME_DETECTION_SNIPPET = dedent(
    """
    <script>
    (function () {
      const sendTheme = (themeValue) => {
        const payload = {theme: themeValue, timestamp: Date.now()};
        if (window.Streamlit && window.Streamlit.setComponentValue) {
          window.Streamlit.setComponentValue(payload);
        }
      };

      const markReady = () => {
        if (window.Streamlit && window.Streamlit.setComponentReady) {
          window.Streamlit.setComponentReady();
        }
      };

      const resolveTheme = (matchesDark) => (matchesDark ? "dark" : "light");

      const readThemeFromDoc = (doc) => {
        const attrTheme =
          doc.getAttribute("data-base-theme") || doc.getAttribute("data-theme");
        if (attrTheme === "light" || attrTheme === "dark") {
          return attrTheme;
        }
        const datasetTheme = (doc.dataset || {}).baseTheme || (doc.dataset || {}).theme;
        if (datasetTheme === "light" || datasetTheme === "dark") {
          return datasetTheme;
        }
        return null;
      };

      const getDomTheme = () => {
        // 1) try parent (Streamlit host document)
        try {
          if (window.parent && window.parent !== window && window.parent.document) {
            const parentTheme = readThemeFromDoc(
              window.parent.document.documentElement
            );
            if (parentTheme) return parentTheme;
          }
        } catch (e) {
          // Cross-origin iframe; ignore and fall back to local document
        }
        // 2) fallback to component iframe document
        return readThemeFromDoc(document.documentElement);
      };

      const sendCurrentTheme = () => {
        const domTheme = getDomTheme();
        if (domTheme) {
          sendTheme(domTheme);
          return domTheme;
        }
        if (window.matchMedia) {
          const mediaQueryList = window.matchMedia("(prefers-color-scheme: dark)");
          const inferred = resolveTheme(mediaQueryList.matches);
          sendTheme(inferred);
          return inferred;
        }
        sendTheme("light");
        return "light";
      };

      const attachDomObserver = () => {
        if (!("MutationObserver" in window)) return;
        const targets = [];
        try {
          if (window.parent && window.parent !== window && window.parent.document) {
            targets.push(window.parent.document.documentElement);
          }
        } catch (e) {
          // Cross-origin iframe; skip parent observer
        }
        targets.push(document.documentElement);

        targets.forEach((doc) => {
          const observer = new MutationObserver(() => {
            const domTheme = getDomTheme();
            if (domTheme) {
              sendTheme(domTheme);
            }
          });
          observer.observe(doc, {
            attributes: true,
            attributeFilter: ["data-base-theme", "data-theme"],
          });
        });
      };

      const attachMediaListener = (mediaQueryList) => {
        const listener = (event) => {
          const isDark =
            event && typeof event.matches === "boolean"
              ? event.matches
              : mediaQueryList.matches;
          sendTheme(resolveTheme(isDark));
        };
        if (mediaQueryList.addEventListener) {
          mediaQueryList.addEventListener("change", listener);
        } else if (mediaQueryList.addListener) {
          mediaQueryList.addListener(listener);
        }
      };

      const init = () => {
        sendCurrentTheme();
        markReady();

        // Track user toggles in Streamlit (data-theme changes)
        attachDomObserver();

        // Track OS-level changes when user chooses “system” in Streamlit
        if (window.matchMedia) {
          const mediaQueryList = window.matchMedia("(prefers-color-scheme: dark)");
          attachMediaListener(mediaQueryList);
        }
      };

      if (window.Streamlit) {
        init();
      } else {
        window.addEventListener("load", init, {once: true});
      }
    })();
    </script>
    """
)


def _resolve_theme_support() -> bool:
    try:
        signature = inspect.signature(st.set_page_config)
    except (TypeError, ValueError):
        return False
    return "theme" in signature.parameters


_SET_PAGE_CONFIG_ACCEPTS_THEME = _resolve_theme_support()


def _normalize_theme(value: Any) -> str | None:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("light", "dark"):
            return lowered
    return None


def detect_browser_theme() -> str | None:
    from src.common.perf import time_block

    with time_block("ensure_auto_theme.components_html", metadata={"phase": "ui"}):
        try:
            payload = components.html(  # type: ignore[call-arg]
                _THEME_DETECTION_SNIPPET,
                height=0,
                width=0,
                key=AUTO_THEME_COMPONENT_KEY,
            )
        except Exception:
            return None
    theme_value = payload.get("theme") if isinstance(payload, dict) else payload
    return _normalize_theme(theme_value)


def ensure_auto_theme(
    *, page_title: str, layout: str = "centered", **page_config: Any
) -> str:
    from src.common.perf import record_event, time_block

    storage = getattr(st, "session_state", None)
    manager = get_session_manager(storage)

    if storage is not None and AUTO_THEME_STATE_KEY in storage:
        existing = _normalize_theme(storage.get(AUTO_THEME_STATE_KEY))
        if existing:
            manager.set_theme_base(existing)
            storage[AUTO_THEME_STATE_KEY] = existing

    stored_theme = _normalize_theme(manager.get_theme_base())
    base_theme = stored_theme or DEFAULT_THEME_BASE

    detection_state = manager.get_theme_detection_state()
    if detection_state not in {
        _DETECTION_STATE_PENDING,
        _DETECTION_STATE_ACTIVE,
        _DETECTION_STATE_DONE,
        _DETECTION_STATE_FAILED,
    }:
        detection_state = _DETECTION_STATE_PENDING
        manager.set_theme_detection_state(detection_state)

    attempts = manager.get_theme_detection_attempts()

    theme_config = dict(page_config.pop("theme", {}))
    theme_config.setdefault("base", base_theme)

    applied_base = manager.get_theme_applied_base()
    configured = manager.is_theme_configured()
    desired_base = theme_config.get("base", DEFAULT_THEME_BASE)

    if not _SET_PAGE_CONFIG_ACCEPTS_THEME and desired_base:
        with suppress(Exception):
            st_config.set_option("theme.base", desired_base)

    if (not configured) or (applied_base != desired_base):
        layout_value = cast(Literal["centered", "wide"], layout)
        if _SET_PAGE_CONFIG_ACCEPTS_THEME:
            st.set_page_config(  # type: ignore[call-arg]
                page_title=page_title,
                layout=layout_value,
                theme=theme_config,
                **page_config,
            )
        else:
            st.set_page_config(
                page_title=page_title, layout=layout_value, **page_config
            )
        manager.set_theme_configured(True)
        manager.set_theme_applied_base(desired_base)

    def _persist_theme(base: str) -> None:
        if storage is not None:
            storage[AUTO_THEME_STATE_KEY] = base

    disable_detection = os.getenv("SOL_PFMEA_DISABLE_THEME_DETECT", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if disable_detection:
        manager.set_theme_detection_state(_DETECTION_STATE_DONE)
        resolved_base = str(theme_config.get("base", base_theme))
        _persist_theme(resolved_base)
        return resolved_base

    if detection_state == _DETECTION_STATE_DONE:
        resolved_base = str(theme_config.get("base", base_theme))
        _persist_theme(resolved_base)
        return resolved_base

    if (
        detection_state in {_DETECTION_STATE_PENDING, _DETECTION_STATE_ACTIVE}
        and attempts >= _DETECTION_MAX_ATTEMPTS
    ):
        manager.set_theme_detection_state(_DETECTION_STATE_FAILED)
        resolved_base = str(theme_config.get("base", base_theme))
        _persist_theme(resolved_base)
        return resolved_base

    detected_theme: str | None = None
    if detection_state != _DETECTION_STATE_DONE:
        if detection_state == _DETECTION_STATE_PENDING:
            manager.set_theme_detection_state(_DETECTION_STATE_ACTIVE)
        manager.increment_theme_detection_attempts()
        with time_block(
            "ensure_auto_theme.detect_browser_theme",
            metadata={"phase": "ui", "attempt": attempts + 1},
        ):
            detected_theme = detect_browser_theme()

    if detected_theme:
        manager.set_theme_detection_state(_DETECTION_STATE_DONE)
        manager.set_theme_base(detected_theme)
        _persist_theme(detected_theme)
        if detected_theme != theme_config.get("base"):
            record_event(
                "ensure_auto_theme.apply_detected_theme",
                metadata={"phase": "ui", "theme": detected_theme},
            )
            manager.set_theme_configured(False)
            if hasattr(st, "rerun"):
                st.rerun()
            else:  # pragma: no cover - fallback for older Streamlit
                st.experimental_rerun()  # type: ignore[attr-defined]
        return detected_theme

    resolved_base = str(theme_config.get("base", base_theme))
    _persist_theme(resolved_base)
    return resolved_base


# Design system styles cache
_DESIGN_SYSTEM_STYLES_APPLIED_KEY = "_design_system_styles_applied"


def apply_design_system_styles(*, force: bool = False) -> None:
    """Apply design system CSS styles to the Streamlit app.

    This function should be called after ensure_auto_theme() to apply
    the design system's CSS variables and base styles. It also injects
    responsive styles for Streamlit widgets.

    Args:
        force: If True, reapply styles even if already applied in this session.

    Example:
        ensure_auto_theme(page_title="PFMEA", layout="wide")
        apply_design_system_styles()
    """
    from src.ui.design_system import (
        inject_accessibility_styles,
        inject_responsive_styles,
    )

    storage = getattr(st, "session_state", None)
    if (
        storage is not None
        and not force
        and storage.get(_DESIGN_SYSTEM_STYLES_APPLIED_KEY)
    ):
        return

    # Load CSS from design system
    css_path = Path(__file__).parent / "styles" / "base.css"
    if css_path.exists():
        css_content = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

    # Inject responsive styles for Streamlit widgets
    inject_responsive_styles()

    # Inject accessibility styles for Streamlit widgets
    inject_accessibility_styles()

    # Mark as applied
    if storage is not None:
        storage[_DESIGN_SYSTEM_STYLES_APPLIED_KEY] = True


def get_current_theme() -> str:
    """Get the current theme (light or dark).

    Returns:
        Theme name: "light" or "dark".
    """
    storage = getattr(st, "session_state", None)
    if storage is not None:
        theme = storage.get(AUTO_THEME_STATE_KEY)
        if isinstance(theme, str) and theme in ("light", "dark"):
            return theme
    return DEFAULT_THEME_BASE


__all__ = [
    "AUTO_THEME_COMPONENT_KEY",
    "AUTO_THEME_STATE_KEY",
    "DEFAULT_THEME_BASE",
    "apply_design_system_styles",
    "detect_browser_theme",
    "ensure_auto_theme",
    "get_current_theme",
]
