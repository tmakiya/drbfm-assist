"""PFMEA Function Mapping詳細ログ記録システム

このモジュールは、PFMEA Function Mappingプロセス中に発生するインデックス補正や
エラー情報を詳細に記録し、後でCSV形式でエクスポートできるようにします。
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class CorrectionType(Enum):
    """インデックス補正のタイプ"""

    OVER_UPPER_BOUND = "上限超過"
    BELOW_LOWER_BOUND = "下限未満"
    INVALID_FORMAT = "不正フォーマット"
    MISSING_VALUE = "値欠落"
    DUPLICATE_ASSIGNMENT = "重複割当"
    OUT_OF_RANGE = "範囲外"


@dataclass
class IndexCorrectionLog:
    """インデックス補正の詳細ログエントリ"""

    # 基本情報
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    process_name: str = ""
    change_id: str = ""
    requirement_index: int = 0

    # 補正情報
    correction_type: str = ""
    field_name: str = ""  # "function_index", "assurance_index", "requirement_index"

    # 値の詳細
    original_value: Any = None
    corrected_value: Any = None
    upper_bound: int = 0
    lower_bound: int = 1

    # コンテキスト情報
    function_list: list[str] = field(default_factory=list)
    assurance_list: list[str] = field(default_factory=list)
    requirement_text: str = ""

    # AI応答情報
    ai_response_entry: dict[str, Any] = field(default_factory=dict)
    raw_json_fragment: str = ""

    # エラー詳細
    error_message: str = ""
    retry_attempt: int = 0
    recovery_method: str = ""  # "retry", "chunk", "placeholder"

    # 追加メタデータ
    chunk_info: dict[str, Any] = field(default_factory=dict)  # チャンク処理時の情報
    session_id: str = ""
    model_name: str = ""


class PFMEAMappingLogger:
    """PFMEA Function Mapping用の詳細ログ管理クラス"""

    def __init__(self) -> None:
        self._logs: list[IndexCorrectionLog] = []
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._model_name = ""

    def set_session_info(
        self, session_id: str | None = None, model_name: str = ""
    ) -> None:
        """セッション情報を設定"""
        if session_id:
            self._session_id = session_id
        self._model_name = model_name

    def log_index_correction(
        self,
        *,
        process_name: str,
        change_id: str,
        field_name: str,
        original_value: Any,
        corrected_value: Any,
        upper_bound: int,
        correction_type: CorrectionType,
        requirement_index: int = 0,
        requirement_text: str = "",
        function_list: list[str] | None = None,
        assurance_list: list[str] | None = None,
        ai_response_entry: dict[str, Any] | None = None,
        raw_json_fragment: str = "",
        retry_attempt: int = 0,
        recovery_method: str = "",
        chunk_info: dict[str, Any] | None = None,
    ) -> None:
        """インデックス補正のログを記録"""

        log_entry = IndexCorrectionLog(
            timestamp=datetime.now().isoformat(),
            process_name=process_name,
            change_id=change_id,
            requirement_index=requirement_index,
            correction_type=correction_type.value,
            field_name=field_name,
            original_value=original_value,
            corrected_value=corrected_value,
            upper_bound=upper_bound,
            lower_bound=1,
            function_list=function_list or [],
            assurance_list=assurance_list or [],
            requirement_text=requirement_text,
            ai_response_entry=ai_response_entry or {},
            raw_json_fragment=raw_json_fragment,
            error_message=self._build_error_message(
                field_name,
                original_value,
                corrected_value,
                upper_bound,
                correction_type,
            ),
            retry_attempt=retry_attempt,
            recovery_method=recovery_method,
            chunk_info=chunk_info or {},
            session_id=self._session_id,
            model_name=self._model_name,
        )

        self._logs.append(log_entry)

        # CLIログにも出力
        logger.warning(
            "PFMEA function mapping %s index %s が%sため補正しました。"
            "\n  詳細: process=%s, change_id=%s, requirement_index=%s"
            "\n  元の値: %s, 補正後: %s, 上限: %s"
            "\n  要求事項: %s"
            "\n  リトライ: %s, 復旧方法: %s",
            field_name,
            original_value,
            self._get_correction_reason(correction_type, upper_bound),
            process_name,
            change_id,
            requirement_index,
            original_value,
            corrected_value,
            upper_bound,
            requirement_text[:50] + "..."
            if len(requirement_text) > 50
            else requirement_text,
            retry_attempt,
            recovery_method,
        )

    def log_index_error(
        self,
        *,
        process_name: str,
        change_id: str,
        field_name: str,
        original_value: Any,
        upper_bound: int,
        requirement_index: int = 0,
        requirement_text: str = "",
        function_list: list[str] | None = None,
        assurance_list: list[str] | None = None,
        ai_response_entry: dict[str, Any] | None = None,
        raw_json_fragment: str = "",
        retry_attempt: int = 0,
        recovery_method: str = "",
        chunk_info: dict[str, Any] | None = None,
    ) -> None:
        """補正せずに失敗したインデックスエラーを記録"""
        log_entry = IndexCorrectionLog(
            timestamp=datetime.now().isoformat(),
            process_name=process_name,
            change_id=change_id,
            requirement_index=requirement_index,
            correction_type=CorrectionType.OUT_OF_RANGE.value,
            field_name=field_name,
            original_value=original_value,
            corrected_value=None,
            upper_bound=upper_bound,
            lower_bound=1,
            function_list=function_list or [],
            assurance_list=assurance_list or [],
            requirement_text=requirement_text,
            ai_response_entry=ai_response_entry or {},
            raw_json_fragment=raw_json_fragment,
            error_message=(
                f"PFMEA function mapping {field_name} index {original_value} が"
                f"{self._get_correction_reason(CorrectionType.OUT_OF_RANGE, upper_bound)}ため"
                "補正せずに失敗しました。"
            ),
            retry_attempt=retry_attempt,
            recovery_method=recovery_method,
            chunk_info=chunk_info or {},
            session_id=self._session_id,
            model_name=self._model_name,
        )

        self._logs.append(log_entry)

        logger.warning(
            "PFMEA function mapping %s index %s が範囲外のため補正せず失敗しました。"
            "\n  詳細: process=%s, change_id=%s, requirement_index=%s"
            "\n  上限: %s"
            "\n  要求事項: %s"
            "\n  リトライ: %s, 復旧方法: %s",
            field_name,
            original_value,
            process_name,
            change_id,
            requirement_index,
            upper_bound,
            requirement_text[:50] + "..."
            if len(requirement_text) > 50
            else requirement_text,
            retry_attempt,
            recovery_method,
        )

    def _build_error_message(
        self,
        field_name: str,
        original_value: Any,
        corrected_value: Any,
        upper_bound: int,
        correction_type: CorrectionType,
    ) -> str:
        """エラーメッセージを構築"""
        return (
            f"PFMEA function mapping {field_name} index {original_value} が"
            f"{self._get_correction_reason(correction_type, upper_bound)}ため"
            f"{corrected_value}に補正しました。"
        )

    def _get_correction_reason(
        self, correction_type: CorrectionType, upper_bound: int
    ) -> str:
        """補正理由の文字列を取得"""
        if correction_type == CorrectionType.OVER_UPPER_BOUND:
            return f"上限 {upper_bound} を超えた"
        elif correction_type == CorrectionType.BELOW_LOWER_BOUND:
            return "下限 1 を下回った"
        elif correction_type == CorrectionType.INVALID_FORMAT:
            return "不正な形式だった"
        elif correction_type == CorrectionType.MISSING_VALUE:
            return "欠落していた"
        elif correction_type == CorrectionType.DUPLICATE_ASSIGNMENT:
            return "重複していた"
        elif correction_type == CorrectionType.OUT_OF_RANGE:
            return "範囲外だった"
        else:  # pragma: no cover
            return "不明なエラーが発生した"

    def get_logs_as_dataframe(self) -> pd.DataFrame:
        """ログをPandas DataFrameとして取得"""
        if not self._logs:
            return pd.DataFrame()

        # dataclassをdictに変換し、リストや辞書を文字列化
        records = []
        for log in self._logs:
            record = asdict(log)
            # リストや辞書を読みやすい形式に変換
            record["function_list"] = "\n".join(record["function_list"])
            record["assurance_list"] = "\n".join(record["assurance_list"])
            record["ai_response_entry"] = json.dumps(
                record["ai_response_entry"], ensure_ascii=False, indent=2
            )
            record["chunk_info"] = json.dumps(
                record["chunk_info"], ensure_ascii=False, indent=2
            )
            records.append(record)

        return pd.DataFrame(records)

    def export_to_csv(self, file_path: Path | str | None = None) -> str:
        """ログをCSV形式でエクスポート

        Args:
            file_path: 保存先ファイルパス。Noneの場合は文字列として返す

        Returns:
            CSV形式の文字列（file_pathが指定された場合も返す）
        """
        df = self.get_logs_as_dataframe()

        # 列の順序を整理
        columns = [
            "timestamp",
            "session_id",
            "model_name",
            "process_name",
            "change_id",
            "requirement_index",
            "field_name",
            "correction_type",
            "original_value",
            "corrected_value",
            "upper_bound",
            "lower_bound",
            "error_message",
            "requirement_text",
            "function_list",
            "assurance_list",
            "retry_attempt",
            "recovery_method",
            "ai_response_entry",
            "raw_json_fragment",
            "chunk_info",
        ]

        # 存在する列のみを選択
        available_columns = [col for col in columns if col in df.columns]
        df = df[available_columns]

        # CSVに変換
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
        csv_content = csv_buffer.getvalue()

        # ファイルに保存（指定された場合）
        if file_path:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(csv_content, encoding="utf-8")
            logger.info(f"PFMEA mapping logs exported to: {path}")

        return csv_content

    def get_summary_statistics(self) -> dict[str, Any]:
        """ログの統計情報を取得"""
        if not self._logs:
            return {
                "total_corrections": 0,
                "by_field": {},
                "by_correction_type": {},
                "by_process": {},
                "by_recovery_method": {},
            }

        df = self.get_logs_as_dataframe()

        return {
            "total_corrections": len(self._logs),
            "by_field": df["field_name"].value_counts().to_dict(),
            "by_correction_type": df["correction_type"].value_counts().to_dict(),
            "by_process": df["process_name"].value_counts().to_dict(),
            "by_recovery_method": df["recovery_method"].value_counts().to_dict(),
            "retry_attempts": {
                "total": df["retry_attempt"].sum(),
                "average": df["retry_attempt"].mean(),
                "max": df["retry_attempt"].max(),
            },
            "session_id": self._session_id,
            "model_name": self._model_name,
        }

    def clear_logs(self) -> None:
        """ログをクリア"""
        self._logs.clear()

    def __len__(self) -> int:
        """ログエントリ数を返す"""
        return len(self._logs)


# グローバルインスタンス
_mapping_logger = PFMEAMappingLogger()


def get_mapping_logger() -> PFMEAMappingLogger:
    """グローバルなマッピングログインスタンスを取得"""
    return _mapping_logger
