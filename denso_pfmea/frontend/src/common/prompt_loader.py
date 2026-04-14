from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parents[2] / "config" / "prompts"


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


@lru_cache(maxsize=8)
def load_prompt_template(name: str) -> PromptTemplate:
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"プロンプトテンプレートが見つかりません: {path}")

    raw_text = path.read_text(encoding="utf-8")
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
