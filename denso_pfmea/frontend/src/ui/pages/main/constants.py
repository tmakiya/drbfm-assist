from __future__ import annotations

import os

from src.ui.shared_constants import PFMEA_BLOCKS

# LLM Model Configuration
# 新モデル追加時: VERTEX_MODEL を変更するだけで反映される設計
# 将来的に複数モデルを選択可能にする場合は LLM_MODE_INFO を拡張
VERTEX_MODEL = "gemini-2.5-pro"
DEFAULT_VERTEX_REGION = os.environ.get("GCP_VERTEX_REGION", "us-central1")
PROMPT_TEMPLATE_NAME = "pfmea_assessment"

# Legacy aliases for backward compatibility
DEFAULT_VERTEX_MODEL = VERTEX_MODEL
PRO_VERTEX_MODEL = VERTEX_MODEL

EXPECTED_LLM_HEADERS: tuple[str, ...] = (
    "追加検討ID",
    "工程名",
    "機能",
    "製造保証項目",
    "要求事項（良品条件）",
    "工程故障モード",
    "故障の影響",
    "故障の原因およびメカニズム",
    "判断",
    "追加理由",
    "自信度",
)
EXPECTED_LLM_ROWS: tuple[str, ...] = ()

# LLM Mode Configuration
# 現在は単一モデルのみ。新モデル追加時はここに追加
LLM_MODE_INFO: dict[str, dict[str, str]] = {
    VERTEX_MODEL: {
        "label": "標準モード",
        "description": "Gemini 2.5 Pro による PFMEA 推定",
    },
}

LLM_MODE_ORDER: tuple[str, ...] = tuple(LLM_MODE_INFO.keys())

LLM_MODE_LABELS: dict[str, str] = {
    model: payload["label"] for model, payload in LLM_MODE_INFO.items()
}

__all__ = [
    "DEFAULT_VERTEX_MODEL",
    "DEFAULT_VERTEX_REGION",
    "EXPECTED_LLM_HEADERS",
    "EXPECTED_LLM_ROWS",
    "LLM_MODE_INFO",
    "LLM_MODE_LABELS",
    "LLM_MODE_ORDER",
    "PFMEA_BLOCKS",
    "PROMPT_TEMPLATE_NAME",
    "PRO_VERTEX_MODEL",
    "VERTEX_MODEL",
]
