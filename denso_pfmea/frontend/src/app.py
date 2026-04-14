"""Streamlit エントリーポイント。UI レンダリングは `src.ui.pages.main` に委譲する。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ is None:  # streamlit run src/app.py でパッケージルートを解決
    sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
from streamlit import config as st_config

from src.common.single_instance import ensure_single_instance
from src.common.structured_logging import configure_logging
from src.ui.pages import main as main_page

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _initialize_logging() -> None:
    """Initialize structured logging on first run (Streamlit-safe)."""
    if "logging_initialized" not in st.session_state:
        # Log directory setup
        log_dir = _PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = str(log_dir / "app.log")

        # Log level from environment variable (via settings)
        from src.config import settings

        log_level = getattr(logging, settings.log_level.upper(), logging.WARNING)

        # Initialize logging
        configure_logging(
            level=log_level,
            structured=True,
            log_file=log_file,
        )
        st.session_state.logging_initialized = True

        logger = logging.getLogger(__name__)
        logger.info("Logging initialized", extra={"stage": "startup"})


def _current_server_port() -> int:
    """Return configured Streamlit server port (defaults to 8501)."""
    port = st_config.get_option("server.port")
    try:
        return int(port) if port else 8501
    except (TypeError, ValueError):
        return 8501


def main() -> None:
    port = _current_server_port()
    ok, details = ensure_single_instance(
        project_root=_PROJECT_ROOT,
        lock_name="streamlit.lock",
        lock_scope=f"port-{port}",
    )

    if not ok:
        _initialize_logging()
        logger = logging.getLogger(__name__)
        lock_path = details.get("lock_path", "") if details else ""
        owner = (details or {}).get("owner") if details else None

        logger.error(
            "Single instance guard failed",
            extra={
                "lock_path": lock_path,
                "owner": owner,
                "port": port,
            },
        )

        st.error(
            "同じポートで他のインスタンスが実行中です。別ポートで起動するか、既存プロセスを終了してください。"
        )
        if lock_path:
            st.code(lock_path, language=None)
        if owner:
            pid = owner.get("pid")
            started_at = owner.get("started_at")
            cwd = owner.get("cwd")
            meta_lines = []
            if pid:
                meta_lines.append(f"pid: {pid}")
            if cwd:
                meta_lines.append(f"cwd: {cwd}")
            if started_at:
                meta_lines.append(f"started_at: {started_at}")
            if meta_lines:
                st.code("\n".join(meta_lines), language=None)
        st.stop()

    _initialize_logging()
    main_page.render_main_page()


if __name__ == "__main__":
    main()


__all__ = ["main"]
