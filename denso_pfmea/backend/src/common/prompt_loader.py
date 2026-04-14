from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parents[2] / "config" / "prompts"

# Module-level cache for async loaded templates
_async_template_cache: dict[str, PromptTemplate] = {}


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    body: str

    def render(self, context: Mapping[str, str]) -> str:
        template = Template(self.body)
        return template.substitute(context)


def _parse_template(raw_text: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    for line in raw_text.splitlines():
        if line.startswith("#@"):
            key_value = line[2:].split(":", 1)
            if len(key_value) != 2:
                raise ValueError(f"テンプレートメタデータの形式が不正です: {line}")
            key, value = key_value
            metadata[key.strip()] = value.strip()
        else:
            body_lines.append(line)
    return metadata, "\n".join(body_lines).strip()


def _build_template(name: str, raw_text: str, path: Path) -> PromptTemplate:
    """Parse raw text and build a PromptTemplate instance."""
    metadata, body = _parse_template(raw_text)

    template_name = metadata.get("name")
    if not template_name:
        raise ValueError(f"テンプレート {path} に name メタデータがありません。")
    if template_name != name:
        raise ValueError(
            f"テンプレート名が一致しません: expected {name}, got {template_name}"
        )

    version = metadata.get("version")
    if not version:
        raise ValueError(f"テンプレート {path} に version メタデータがありません。")

    return PromptTemplate(name=template_name, version=version, body=body)


@lru_cache(maxsize=8)
def load_prompt_template(name: str) -> PromptTemplate:
    """同期版プロンプトテンプレート読み込み。

    Note: async コンテキストからは aload_prompt_template を使用してください。
    """
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"プロンプトテンプレートが見つかりません: {path}")

    raw_text = path.read_text(encoding="utf-8")
    return _build_template(name, raw_text, path)


async def aload_prompt_template(name: str) -> PromptTemplate:
    """非同期版プロンプトテンプレート読み込み。

    ファイル読み込みを別スレッドで実行し、イベントループをブロックしません。
    結果はモジュールレベルでキャッシュされます。
    """
    # Check module-level cache first
    if name in _async_template_cache:
        return _async_template_cache[name]

    path = PROMPT_DIR / f"{name}.md"

    # Check file existence in a separate thread to avoid blocking
    exists = await asyncio.to_thread(path.is_file)
    if not exists:
        raise FileNotFoundError(f"プロンプトテンプレートが見つかりません: {path}")

    # Read file in a separate thread to avoid blocking the event loop
    raw_text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    template = _build_template(name, raw_text, path)

    # Cache the result
    _async_template_cache[name] = template

    return template


__all__ = ["PromptTemplate", "load_prompt_template", "aload_prompt_template"]
