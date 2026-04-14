"""Project-wide helpers for loading environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "python-dotenv が見つかりません。'pip install python-dotenv' を実行してください。"
    ) from exc


@dataclass(frozen=True)
class EnvLoadResult:
    """Metadata about the environment file that was loaded."""

    loaded: bool
    source: Path | None
    used_sample: bool = False


def load_project_env(
    *,
    env_path: Path | None = None,
    override: bool = False,
    raise_on_missing: bool = True,
) -> EnvLoadResult:
    """Load environment variables from a `.env` file.

    The file path is determined in the following order:
    1. Explicit `env_path` parameter
    2. `ENV_FILE_PATH` environment variable
    3. `.env` file in the current working directory

    Args:
        env_path: Explicit path to the .env file.
        override: Whether to override existing environment variables.
        raise_on_missing: Whether to raise an error if no .env file is found.

    Returns:
        EnvLoadResult with metadata about the loaded file.
    """
    candidates: list[Path] = []

    # 1. Explicit path
    if env_path is not None:
        candidates.append(env_path)

    # 2. ENV_FILE_PATH environment variable
    env_file_path = os.getenv("ENV_FILE_PATH")
    if env_file_path:
        candidates.append(Path(env_file_path))

    # 3. Current working directory
    candidates.append(Path.cwd() / ".env")

    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=override)
            return EnvLoadResult(loaded=True, source=candidate, used_sample=False)

    if raise_on_missing:
        expected = ", ".join(str(p) for p in candidates)
        raise RuntimeError(f".env ファイルが見つかりません: {expected}")

    return EnvLoadResult(loaded=False, source=None, used_sample=False)


__all__ = [
    "EnvLoadResult",
    "load_project_env",
]
