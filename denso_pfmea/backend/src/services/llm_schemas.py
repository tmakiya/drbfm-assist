"""LLM Structured Output スキーマ定義.

Gemini API の response_schema パラメータで使用するスキーマを定義する。
Pydantic v2 モデルを使用し、JSON Schema への変換をサポートする。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PfmeaAssessmentRow(BaseModel):
    """PFMEA アセスメント結果の1行."""

    model_config = ConfigDict(populate_by_name=True)

    追加検討ID: str = Field(
        description="一意の識別子（例: PFMEA-01, PFMEA-02）",
        examples=["PFMEA-01"],
    )
    工程名: str = Field(
        description="既存PFMEAに記載されている工程名",
        examples=["ケース把持"],
    )
    機能: str = Field(
        description="工程の機能",
        examples=["ケースをガタなく把持する"],
    )
    製造保証項目: str = Field(
        description="製造保証項目",
        examples=["ケース把持力確保"],
    )
    要求事項_良品条件: str = Field(
        alias="要求事項（良品条件）",
        description="良品条件としての要求事項",
        examples=["ガタや傾きが無いこと"],
    )
    工程故障モード: str = Field(
        description="故障モード（複数の場合は<br>区切り）",
        examples=["把持ピン摩耗によりケースが傾く"],
    )
    故障の影響: str = Field(
        description="故障の影響（複数の場合は<br>区切り）",
        examples=["風漏れ／異音／顧客ライン停止の再発リスク"],
    )
    故障の原因およびメカニズム: str = Field(
        description="故障の原因とメカニズム",
        examples=["把持ピン摩耗・バネ荷重低下"],
    )
    判断: Literal["追加不要", "検討候補", "追加推奨"] = Field(
        description="判断結果（追加不要/検討候補/追加推奨のいずれか）",
        examples=["検討候補"],
    )
    追加理由: str = Field(
        description="判断の根拠",
        examples=["重点管理指定あり、この工程では摩耗監視が未記載"],
    )
    自信度: int = Field(
        ge=1,
        le=5,
        description="確信度（1-5の整数）。5=新規リスク確実、1=既存管理で十分",
        examples=[4],
    )


class PfmeaAssessmentResponse(BaseModel):
    """PFMEA アセスメント応答全体."""

    results: list[PfmeaAssessmentRow] = Field(
        description="評価結果の配列",
        min_length=1,
    )


def get_pfmea_assessment_schema() -> dict[str, Any]:
    """PFMEA アセスメント用の JSON Schema を取得する.

    Returns:
        Gemini API の response_schema パラメータで使用可能な辞書形式のスキーマ。
    """
    return PfmeaAssessmentResponse.model_json_schema()


# Gemini API 用に簡略化されたスキーマ（辞書形式）
# Pydantic スキーマが複雑すぎる場合のフォールバック用
PFMEA_ASSESSMENT_SCHEMA_SIMPLE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "追加検討ID": {"type": "string"},
                    "工程名": {"type": "string"},
                    "機能": {"type": "string"},
                    "製造保証項目": {"type": "string"},
                    "要求事項（良品条件）": {"type": "string"},
                    "工程故障モード": {"type": "string"},
                    "故障の影響": {"type": "string"},
                    "故障の原因およびメカニズム": {"type": "string"},
                    "判断": {
                        "type": "string",
                        "enum": ["追加不要", "検討候補", "追加推奨"],
                    },
                    "追加理由": {"type": "string"},
                    "自信度": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": [
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
                ],
                "propertyOrdering": [
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
                ],
            },
        },
    },
    "required": ["results"],
}

# Gemini 2.5+ 向け: propertyOrdering なしの軽量スキーマ
PFMEA_ASSESSMENT_SCHEMA_V2: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "追加検討ID": {"type": "string"},
                    "工程名": {"type": "string"},
                    "機能": {"type": "string"},
                    "製造保証項目": {"type": "string"},
                    "要求事項（良品条件）": {"type": "string"},
                    "工程故障モード": {"type": "string"},
                    "故障の影響": {"type": "string"},
                    "故障の原因およびメカニズム": {"type": "string"},
                    "判断": {
                        "type": "string",
                        "enum": ["追加不要", "検討候補", "追加推奨"],
                    },
                    "追加理由": {"type": "string"},
                    "自信度": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": [
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
                ],
            },
        },
    },
    "required": ["results"],
}


def get_pfmea_assessment_schema_for_model(model_name: str | None) -> dict[str, Any]:
    """モデル名に応じた PFMEA アセスメントスキーマを返す."""
    if not model_name:
        return PFMEA_ASSESSMENT_SCHEMA_SIMPLE
    lowered = str(model_name).lower()
    if "2.5" in lowered or "gemini-3" in lowered:
        return PFMEA_ASSESSMENT_SCHEMA_V2
    return PFMEA_ASSESSMENT_SCHEMA_SIMPLE


###############################################################################
# Function Mapping Schema
###############################################################################


class FunctionMappingRecord(BaseModel):
    """機能マッピング結果の1行."""

    function_index: int = Field(
        ge=1,
        description="工程機能のインデックス（1始まり）",
        examples=[1],
    )
    assurance_index: int = Field(
        ge=0,
        description="製造保証項目のインデックス（0=該当なし、それ以外は1始まり）",
        examples=[1],
    )
    requirement_index: int = Field(
        ge=1,
        description="要求事項のインデックス（1始まり）",
        examples=[1],
    )
    function: str = Field(
        description="工程の機能をそのまま記載",
        examples=["ケースを加工位置まで搬送し、バックアップでケースを保持"],
    )
    assurance: str = Field(
        description="製造保証項目をそのまま記載（該当なしの場合は空文字）",
        examples=["スライドドアギヤズレなきこと"],
    )
    requirement: str = Field(
        description="要求事項をそのまま記載",
        examples=[
            "ケース搬送アタッチメント把持機構が正常に機能し、ケースがガタ無く把持される事 #1"
        ],
    )
    reason: str = Field(
        description="対応付けの根拠（30-120文字）",
        examples=["要求は「把持がズレないこと」なので保証#1に紐づけ"],
    )


class FunctionMappingResponse(BaseModel):
    """機能マッピング応答全体."""

    records: list[FunctionMappingRecord] = Field(
        description="マッピング結果の配列",
        min_length=1,
    )


FUNCTION_MAPPING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "function_index": {"type": "integer", "minimum": 1},
                    "assurance_index": {"type": "integer", "minimum": 0},
                    "requirement_index": {"type": "integer", "minimum": 1},
                    "function": {"type": "string"},
                    "assurance": {"type": "string"},
                    "requirement": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "function_index",
                    "assurance_index",
                    "requirement_index",
                    "function",
                    "assurance",
                    "requirement",
                    "reason",
                ],
                "propertyOrdering": [
                    "function_index",
                    "assurance_index",
                    "requirement_index",
                    "function",
                    "assurance",
                    "requirement",
                    "reason",
                ],
            },
        },
    },
    "required": ["records"],
}


def get_function_mapping_schema(
    *,
    function_count: int,
    assurance_count: int,
    requirement_count: int,
) -> dict[str, Any]:
    """Build a function mapping schema with dynamic index bounds."""
    function_max = max(1, int(function_count))
    requirement_max = max(1, int(requirement_count))
    if assurance_count > 0:
        assurance_min = 1
        assurance_max = int(assurance_count)
    else:
        assurance_min = 0
        assurance_max = 0

    return {
        "type": "object",
        "properties": {
            "records": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "function_index": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": function_max,
                        },
                        "assurance_index": {
                            "type": "integer",
                            "minimum": assurance_min,
                            "maximum": assurance_max,
                        },
                        "requirement_index": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": requirement_max,
                        },
                        "function": {"type": "string"},
                        "assurance": {"type": "string"},
                        "requirement": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "function_index",
                        "assurance_index",
                        "requirement_index",
                        "function",
                        "assurance",
                        "requirement",
                        "reason",
                    ],
                    "propertyOrdering": [
                        "function_index",
                        "assurance_index",
                        "requirement_index",
                        "function",
                        "assurance",
                        "requirement",
                        "reason",
                    ],
                },
            },
        },
        "required": ["records"],
    }


###############################################################################
# Risk Rating Schema
###############################################################################


class RiskRatingRecordSchema(BaseModel):
    """リスク評価結果の1行."""

    行ID: str = Field(
        description="入力で与えられた行ID",
        examples=["rating-001"],
    )
    影響度合: int = Field(
        ge=1,
        le=10,
        description="影響度合（1-10の整数）",
        examples=[7],
    )
    発生度合: int = Field(
        ge=1,
        le=10,
        description="発生度合（1-10の整数）",
        examples=[4],
    )
    検出度合: int = Field(
        ge=1,
        le=10,
        description="検出度合（1-10の整数）",
        examples=[3],
    )
    影響度合の理由: str = Field(
        description="影響度合を設定した理由（1文）",
        examples=["安全部品への影響があり、重大な品質問題となる可能性があるため"],
    )
    発生度合の理由: str = Field(
        description="発生度合を設定した理由（1文）",
        examples=["過去に類似の不具合が月1回程度発生しているため"],
    )
    検出度合の理由: str = Field(
        description="検出度合を設定した理由（1文）",
        examples=["目視検査のみで自動検出手段がないため"],
    )
    根拠: str = Field(
        description="評価理由の総括",
        examples=["変化点による影響度は中程度、既存管理で一部カバー可能"],
    )


class RiskRatingResponseSchema(BaseModel):
    """リスク評価応答全体."""

    工程名: str = Field(
        description="工程名をそのまま再掲",
        examples=["ケース把持"],
    )
    工程の機能: str = Field(
        description="工程の機能をそのまま再掲",
        examples=["ケースをガタなく把持する"],
    )
    評価結果: list[RiskRatingRecordSchema] = Field(
        description="評価結果の配列",
        min_length=1,
    )


RISK_RATING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "工程名": {"type": "string"},
        "工程の機能": {"type": "string"},
        "評価結果": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "行ID": {"type": "string"},
                    "影響度合": {"type": "integer", "minimum": 1, "maximum": 10},
                    "発生度合": {"type": "integer", "minimum": 1, "maximum": 10},
                    "検出度合": {"type": "integer", "minimum": 1, "maximum": 10},
                    "影響度合の理由": {"type": "string"},
                    "発生度合の理由": {"type": "string"},
                    "検出度合の理由": {"type": "string"},
                    "根拠": {"type": "string"},
                },
                "required": [
                    "行ID",
                    "影響度合",
                    "発生度合",
                    "検出度合",
                    "影響度合の理由",
                    "発生度合の理由",
                    "検出度合の理由",
                    "根拠",
                ],
                "propertyOrdering": [
                    "行ID",
                    "影響度合",
                    "発生度合",
                    "検出度合",
                    "影響度合の理由",
                    "発生度合の理由",
                    "検出度合の理由",
                    "根拠",
                ],
            },
        },
    },
    "required": ["工程名", "工程の機能", "評価結果"],
}


__all__ = [
    # PFMEA Assessment
    "PfmeaAssessmentRow",
    "PfmeaAssessmentResponse",
    "get_pfmea_assessment_schema",
    "PFMEA_ASSESSMENT_SCHEMA_SIMPLE",
    "PFMEA_ASSESSMENT_SCHEMA_V2",
    "get_pfmea_assessment_schema_for_model",
    # Function Mapping
    "FunctionMappingRecord",
    "FunctionMappingResponse",
    "FUNCTION_MAPPING_SCHEMA",
    "get_function_mapping_schema",
    # Risk Rating
    "RiskRatingRecordSchema",
    "RiskRatingResponseSchema",
    "RISK_RATING_SCHEMA",
]
