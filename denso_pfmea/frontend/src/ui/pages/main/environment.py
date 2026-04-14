from __future__ import annotations

from src.common.env import EnvLoadResult, load_project_env

_ENV_RESULT: EnvLoadResult | None = None


def ensure_env_loaded() -> EnvLoadResult:
    global _ENV_RESULT
    if _ENV_RESULT is not None:
        return _ENV_RESULT

    # NOTE: Docker 環境では .env ファイルは docker-compose.yml の env_file で渡されるため、
    # ファイルが見つからなくてもエラーにしない。
    # 関連ファイル: src/common/env.py
    _ENV_RESULT = load_project_env(
        raise_on_missing=False,  # Docker 環境対応のため False に変更
    )
    return _ENV_RESULT


__all__ = ["ensure_env_loaded"]
