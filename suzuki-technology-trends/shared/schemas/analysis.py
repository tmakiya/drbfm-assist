"""
分析関連のPydanticスキーマ定義
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """分析リクエスト"""
    topic: str = Field(..., description="分析トピック")
    use_case: str = Field(..., description="ユースケース")
    interest_keywords: List[str] = Field(default_factory=list, description="課題テーマ")
    tech_keywords: List[str] = Field(default_factory=list, description="技術テーマ")
    component_keywords: List[str] = Field(default_factory=list, description="構成品テーマ")
    project_keywords: List[str] = Field(default_factory=list, description="プロジェクト名")
    additional_context: str = Field(default="", description="追加コンテキスト")
    client_id: Optional[str] = Field(None, description="クライアントID（マルチテナンシー用）")


class AnalysisResponse(BaseModel):
    """分析レスポンス"""
    job_id: str = Field(..., description="ジョブID")
    status: str = Field(..., description="ステータス: queued, processing, completed, failed")
    created_at: datetime = Field(default_factory=datetime.now)


class AnalysisProgress(BaseModel):
    """分析進捗状況"""
    job_id: str
    status: str
    progress_percentage: float = Field(0.0, ge=0.0, le=100.0)
    current_step: Optional[str] = None
    expert_team: Optional[List[str]] = None
    turn: Optional[int] = None
    expert_name: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    filtered_document_count: Optional[int] = Field(None, description="フィルター適用後のドキュメント件数")


class AnalysisResult(BaseModel):
    """分析結果"""
    job_id: str
    expert_team: List[Dict[str, str]]
    analysis_results: Dict[str, str]
    final_report: str
    all_references: List[Dict[str, Any]]
    discussion_log: List[Dict[str, Any]]
    created_at: datetime
    completed_at: datetime


class FileUploadResponse(BaseModel):
    """ファイルアップロードレスポンス"""
    file_id: str
    filename: str
    file_type: str
    size: int
    status: str  # uploaded, processing, indexed, failed
    message: Optional[str] = None

