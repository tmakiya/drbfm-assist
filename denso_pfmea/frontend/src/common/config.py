"""Configuration helpers for BOP/PFMEA parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]

from .paths import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "bop_rules.yaml"


@dataclass(frozen=True)
class BopConfig:
    keyword_categories: dict[str, list[str]]
    template_hints: dict[str, str]
    process_rules: list[tuple[str, list[str]]]
    part_skip_patterns: tuple[str, ...]


DEFAULT_BOP_CONFIG = BopConfig(
    keyword_categories={
        "シャフト": ["シャフト", "shaft", "ｼｬﾌﾄ"],
        "ドア": ["ドア", "door", "ﾄﾞｱ"],
        "ケース": ["ケース", "case", "ｹｰｽ"],
        "グリッド": ["グリッド", "グリッ", "grid", "ｸﾞﾘｯﾄﾞ"],
        "ガイド": ["ガイド", "guide", "ｶﾞｲﾄﾞ"],
        "ビス": ["ビス", "ﾋﾞｽ", "タッピング", "六角"],
        "サーボ": ["サーボ", "servo", "ｻｰﾎﾞ"],
        "センサ": ["センサ", "ｾﾝｻ", "センサー"],
    },
    template_hints={
        "シャフト": "ロボットチャックや保持治具の把持力・摩耗状態を点検し、エア圧やスプリングの整備記録を更新する。",
        "ドア": "搬送時の傾きや擦れを再現し、ドア外観と摺動部の干渉チェックを追加する。",
        "ケース": "ケース把持・嵌合治具の基準面とバックアップ圧を確認し、センサ位置校正を見直す。",
        "グリッド": "グリッド組付けの押し込み力と位置決めセンサの閾値を確認し、浮き検知ロジックを点検する。",
        "ガイド": "ガイドの差し込み深さと保持ボルトの締結状態を点検し、ワーク確認センサの受光位置を再調整する。",
        "ビス": "締付けトルクと工具摩耗を点検し、締結後の検査手順（引っ張り・トルク確認）を強化する。",
        "サーボ": "サーボモジュールのI/Fと固定ブラケットの摩耗・緩みを点検する。",
        "センサ": "センサ固定具の緩みや光軸ズレを確認し、自己診断・冗長検知の設定を見直す。",
    },
    process_rules=[
        ("ｴﾗｽﾄﾏﾄﾞｱ/AMｼｬﾌﾄ組付", ["シャフト", "ドア", "エラストマ", "ｴﾗｽﾄﾏ"]),
        ("ｹｰｽ嵌合", ["ケース", "嵌合"]),
        ("温ｺﾝｸﾞﾘｯﾄﾞ組付（設備）セツビ", ["グリッド", "温コン", "温ｺﾝ"]),
        ("温ｺﾝｶﾞｲﾄﾞ組付", ["ガイド", "ガイド", "ｶﾞｲﾄﾞ"]),
    ],
    part_skip_patterns=("供給", "供給口"),
)


def _merge_config(base: BopConfig, data: dict[str, Any]) -> BopConfig:
    keyword_categories = {
        **base.keyword_categories,
        **data.get("keyword_categories", {}),
    }
    template_hints = {**base.template_hints, **data.get("template_hints", {})}

    if "process_rules" in data:
        process_rules: list[tuple[str, list[str]]] = []
        for rule in data["process_rules"]:
            name = rule.get("name")
            keywords = rule.get("keywords", [])
            if name and keywords:
                process_rules.append((name, list(keywords)))
    else:
        process_rules = list(base.process_rules)

    skip_patterns = tuple(data.get("part_skip_patterns", base.part_skip_patterns))

    return BopConfig(
        keyword_categories=keyword_categories,
        template_hints=template_hints,
        process_rules=process_rules,
        part_skip_patterns=skip_patterns,
    )


def load_bop_config(path: Path | None = None) -> BopConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"BOP設定ファイルが見つかりません: {config_path}")

    raw_text = config_path.read_text(encoding="utf-8")
    data: dict[str, Any]
    if yaml is not None:
        try:
            data = yaml.safe_load(raw_text) or {}
        except (
            yaml.YAMLError
        ) as exc:  # pragma: no cover - only triggered with YAML installed
            raise ValueError(
                f"設定ファイル {config_path} の読み込みに失敗しました: {exc}"
            ) from exc
    else:
        data = json.loads(raw_text or "{}")
    return _merge_config(DEFAULT_BOP_CONFIG, data)
