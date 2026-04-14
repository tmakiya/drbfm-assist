"""Process-level single-instance guard for Streamlit runtime."""

from __future__ import annotations

import atexit
import json
import os
import time
from pathlib import Path
from typing import Any


class SingleInstanceGuard:
    """Lock-file based guard with stale-lock detection."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._acquired = False

    def acquire(self) -> bool:
        if self._acquired:
            return True

        # Check if existing lock belongs to current process (Streamlit rerun)
        if self._is_own_lock():
            self._acquired = True
            atexit.register(self.release)
            return True

        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale():
                    try:
                        self._lock_path.unlink(missing_ok=True)
                    except OSError:
                        return False
                    continue
                return False

            try:
                payload = {
                    "pid": os.getpid(),
                    "started_at": time.time(),
                    "cwd": str(Path.cwd()),
                }
                os.write(fd, json.dumps(payload).encode("utf-8"))
            finally:
                os.close(fd)

            self._acquired = True
            atexit.register(self.release)
            return True

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            self._lock_path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def _read_payload(self) -> dict[str, Any] | None:
        try:
            result: dict[str, Any] = json.loads(
                self._lock_path.read_text(encoding="utf-8")
            )
            return result
        except (OSError, json.JSONDecodeError):
            return None

    def _is_own_lock(self) -> bool:
        payload = self._read_payload()
        if not payload:
            return False
        return payload.get("pid") == os.getpid()

    def _is_stale(self) -> bool:
        payload = self._read_payload()
        if not payload:
            return False

        pid = payload.get("pid")
        if not isinstance(pid, int):
            return False

        return not _process_alive(pid)

    def current_owner(self) -> dict[str, Any] | None:
        payload = self._read_payload()
        if not payload:
            return None

        owner: dict[str, Any] = {}
        if isinstance(payload.get("pid"), int):
            owner["pid"] = payload["pid"]
        if isinstance(payload.get("cwd"), str):
            owner["cwd"] = payload["cwd"]
        if isinstance(payload.get("started_at"), (int, float)):
            owner["started_at"] = payload["started_at"]

        return owner or None


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def ensure_single_instance(
    *,
    project_root: Path,
    lock_name: str,
    lock_scope: str | None = None,
    allow_env: str = "SOL_PFMEA_ALLOW_MULTI_INSTANCE",
) -> tuple[bool, dict[str, Any] | None]:
    if os.getenv(allow_env):
        return True, {"disabled_by": allow_env}

    lock_dir = project_root / "runtime" / "locks"
    if lock_scope:
        safe_scope = lock_scope.replace(os.sep, "_")
        if os.altsep:
            safe_scope = safe_scope.replace(os.altsep, "_")
        lock_dir = lock_dir / safe_scope

    lock_path = lock_dir / lock_name
    guard = SingleInstanceGuard(lock_path)
    if guard.acquire():
        return True, {"lock_path": str(lock_path)}

    details: dict[str, Any] = {"lock_path": str(lock_path)}
    # Fake guards used in tests may not implement current_owner; guard against AttributeError.
    owner_fn = getattr(guard, "current_owner", None)
    owner = owner_fn() if callable(owner_fn) else None
    if owner:
        details["owner"] = owner

    return False, details


__all__ = ["SingleInstanceGuard", "ensure_single_instance"]
