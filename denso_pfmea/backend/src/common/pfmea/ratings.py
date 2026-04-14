from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from src.common.text_utils import sanitize

from .constants import DEFAULT_RATINGS_PATH
from .models import RatingScales


def _load_rating_scales(path: Path = DEFAULT_RATINGS_PATH) -> RatingScales:
    if not path.is_file():
        raise FileNotFoundError(
            f"PFMEA評価スケール設定ファイルが見つかりません: {path}"
        )
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(
            f"PFMEA評価スケール設定ファイルの読み取りに失敗しました: {path}"
        ) from exc

    severity_data = data.get("severity") or {}
    occurrence_data = data.get("occurrence") or {}
    detection_data = data.get("detection") or {}

    if not (severity_data and occurrence_data and detection_data):
        raise ValueError(
            f"PFMEA評価スケール設定ファイルに必須項目が不足しています: {path}"
        )

    try:
        severity = {int(k): str(v) for k, v in severity_data.items()}
        occurrence = {int(k): str(v) for k, v in occurrence_data.items()}
        detection = {int(k): str(v) for k, v in detection_data.items()}
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"PFMEA評価スケール設定ファイルの評価値が不正です: {path}"
        ) from exc

    return RatingScales(severity=severity, occurrence=occurrence, detection=detection)


DEFAULT_RATING_SCALES = _load_rating_scales()


def _clean_rating_text(score: int, text: str) -> tuple[str, str]:
    cleaned = sanitize(text)
    prefix = str(score)
    if cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix) :].lstrip(" ：:　")
    if "：" in cleaned:
        summary, detail = cleaned.split("：", 1)
    elif " " in cleaned:
        summary, detail = cleaned.split(" ", 1)
    else:
        summary = cleaned
        detail = ""
    summary = summary.strip()
    detail = detail.strip()
    return summary, detail


def build_rating_markdown(scale: Mapping[int, str], header: str) -> str:
    rows = ["|評価|概要|詳細|", "|---|---|---|"]
    for score in sorted(scale.keys()):
        summary, detail = _clean_rating_text(score, scale[score])
        rows.append(f"|{score}|{summary}|{detail or '―'}|")
    table = "\n".join(rows)
    return f"**{header}**\n\n{table}"


__all__ = ["DEFAULT_RATING_SCALES", "build_rating_markdown"]
