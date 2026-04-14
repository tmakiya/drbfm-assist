"""Frontend 用の軽量版 risk_rating モジュール。

LLM 依存を排除し、データクラス（型定義）のみを提供します。
LLM 処理は Backend で行われます。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskRatingRow:
    """評価対象となる PFMEA 行のサマリ。"""

    rating_id: str
    requirement: str
    failure_mode: str
    effect: str
    cause: str
    judgement: str
    reason: str
    prevention: str = ""
    detection_method: str = ""
    recommended_action: str = ""
    additional_notes: str = ""


@dataclass(frozen=True)
class RiskRatingGroup:
    """工程の機能単位で束ねた評価リクエスト。"""

    group_id: str
    process_name: str
    process_function: str
    assurances: tuple[str, ...]
    rows: tuple[RiskRatingRow, ...]
    change_summaries: tuple[str, ...] = ()
    baseline_examples: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class RiskRatingRecord:
    """単一行の評価結果。"""

    rating_id: str
    impact: int
    occurrence: int
    detection: int
    rationale: str
    impact_reason: str = ""
    occurrence_reason: str = ""
    detection_reason: str = ""

    def formatted_indicator_rationale(self) -> str:
        """Format per-indicator rationale sentences joined by newline."""

        def _normalize_sentence(text: str, label: str) -> str:
            stripped = text.strip()
            if not stripped:
                stripped = (
                    self.rationale.strip() or f"{label}の根拠情報が提供されていません。"
                )
            if stripped.endswith(("。", "！", "!", "？", "?", ".")):
                return stripped
            return f"{stripped}。"

        sentences: list[str] = []
        for label, score, reason in (
            ("影響度合", self.impact, self.impact_reason),
            ("発生度合", self.occurrence, self.occurrence_reason),
            ("検出度合", self.detection, self.detection_reason),
        ):
            detail = _normalize_sentence(reason, label)
            sentences.append(f"{label}({score}): {detail}")
        return "\n".join(sentences)


@dataclass(frozen=True)
class RiskRatingResponse:
    group_id: str
    records: tuple[RiskRatingRecord, ...]
    raw_text: str = ""


class RiskRatingError(RuntimeError):
    """リスク評価ステージの基底例外。"""


class MalformedRiskRatingResponseError(RiskRatingError):
    """AI応答が JSON として解釈できない場合の例外。"""

    def __init__(self, message: str, *, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


__all__ = [
    "RiskRatingError",
    "RiskRatingGroup",
    "RiskRatingRecord",
    "RiskRatingResponse",
    "RiskRatingRow",
    "MalformedRiskRatingResponseError",
]
