"""
設定ファイル: 環境変数とアプリケーション設定を管理

本番環境アーキテクチャ対応:
- Agent UI Infrastructure (AURA) System: UI Application
- LangGraph Platform: Agent/AI workflow
- LangSmith: Deployment管理
- Search Platform: Elasticsearch検索
- AuthN Platform: 認証（Drawer連携）
"""
import os
from pathlib import Path
from typing import Optional, List, Union
from pydantic_settings import BaseSettings
from pydantic import field_validator
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """アプリケーション設定"""
    
    # ===========================================================================
    # 環境設定
    # ===========================================================================
    # development: 開発環境（FAISS, ローカル認証）
    # production: 本番環境（Elasticsearch, AuthN Platform, LangGraph Platform）
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # マルチテナント設定
    TENANT_ID: str = os.getenv("TENANT_ID", "default")
    APP_NAME: str = os.getenv("APP_NAME", "drawer-ai-tech-review")
    
    # API設定
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "DrawerAI Technology Review System"
    VERSION: str = "2.0.0"
    
    # ===========================================================================
    # セキュリティ設定
    # ===========================================================================
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # AuthN Platform設定（本番環境用）
    AUTHN_PLATFORM_URL: Optional[str] = os.getenv("AUTHN_PLATFORM_URL")
    AUTHN_INTERNAL_TOKEN: Optional[str] = os.getenv("AUTHN_INTERNAL_TOKEN")
    
    # CORS設定
    CORS_ORIGINS: Union[str, List[str]] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000"
    )
    
    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """CORS_ORIGINSをリストに変換"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # ===========================================================================
    # LLM設定
    # ===========================================================================
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    LLM_MODEL_NAME_FLASH: str = os.getenv("LLM_MODEL_NAME_FLASH", "gemini-2.5-flash")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "models/embedding-001")
    
    # ===========================================================================
    # LangGraph Platform / LangSmith設定（本番環境用）
    # ===========================================================================
    LANGGRAPH_SERVER_URL: Optional[str] = os.getenv("LANGGRAPH_SERVER_URL")
    LANGSMITH_API_KEY: Optional[str] = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "drawer-ai-tech-review")
    LANGSMITH_ENDPOINT: str = os.getenv("LANGSMITH_ENDPOINT", "https://langsmith.zoolake.jp")
    WORKFLOW_NAME: str = os.getenv("WORKFLOW_NAME", "tech-review-workflow")
    
    # ===========================================================================
    # データベース設定
    # ===========================================================================
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/drawerai"
    )
    
    # ===========================================================================
    # 検索システム設定（ISP - Interactive Search Platform）
    # ===========================================================================
    # 検索バックエンド: isp（推奨）, faiss（レガシー）, elasticsearch（レガシー）
    SEARCH_BACKEND: str = os.getenv("SEARCH_BACKEND", "isp")

    # ISP設定（Interactive Search Platform）
    ISP_URL: str = os.getenv("ISP_URL", "http://localhost:50080")
    ISP_TENANT_ID: Optional[str] = os.getenv("ISP_TENANT_ID")
    ISP_INDEX_ALIAS: str = os.getenv("ISP_INDEX_ALIAS", "tech_trends")
    ISP_AUTH_TOKEN: Optional[str] = os.getenv("ISP_AUTH_TOKEN")
    ISP_VECTOR_FIELD: str = os.getenv("ISP_VECTOR_FIELD", "embedding")
    ISP_VECTOR_DIMS: int = int(os.getenv("ISP_VECTOR_DIMS", "768"))  # Gemini embedding dimension

    # レガシー: FAISS設定（開発環境用 - 非推奨）
    VECTOR_DB_TYPE: str = os.getenv("VECTOR_DB_TYPE", "faiss")
    QDRANT_URL: Optional[str] = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")

    # レガシー: Elasticsearch設定（本番環境用 - 非推奨）
    ELASTICSEARCH_URL: Optional[str] = os.getenv("ELASTICSEARCH_URL")
    ELASTICSEARCH_API_KEY: Optional[str] = os.getenv("ELASTICSEARCH_API_KEY")
    ELASTICSEARCH_INDEX_PREFIX: str = os.getenv("ELASTICSEARCH_INDEX_PREFIX", "drawer-ai")
    
    # ===========================================================================
    # MSQP / Catalyst設定（本番環境用 - データソース）
    # ===========================================================================
    MSQP_ENDPOINT: Optional[str] = os.getenv("MSQP_ENDPOINT")
    CATALYST_ENDPOINT: Optional[str] = os.getenv("CATALYST_ENDPOINT")
    
    # ===========================================================================
    # Redis設定（Celery用）
    # ===========================================================================
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # ===========================================================================
    # ストレージ設定
    # ===========================================================================
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "./uploads"))
    RAG_INDEX_DIR: Path = Path(os.getenv("RAG_INDEX_DIR", "./rag_indices"))
    
    # ファイル設定
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: list = [".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg"]
    
    # ===========================================================================
    # 分析設定
    # ===========================================================================
    MAX_EXPERTS: int = 3
    DEFAULT_DISCUSSION_TURNS: int = 2
    RAG_SEARCH_K: int = 5
    
    # ===========================================================================
    # ロギング設定
    # ===========================================================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # ===========================================================================
    # ヘルパーメソッド
    # ===========================================================================
    @property
    def is_production(self) -> bool:
        """本番環境かどうか"""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        """開発環境かどうか"""
        return self.ENVIRONMENT == "development"
    
    @property
    def use_isp(self) -> bool:
        """ISP (Interactive Search Platform) を使用するかどうか"""
        return self.SEARCH_BACKEND == "isp"

    @property
    def use_elasticsearch(self) -> bool:
        """Elasticsearchを使用するかどうか（レガシー）"""
        return self.SEARCH_BACKEND == "elasticsearch" or (
            self.is_production and self.ELASTICSEARCH_URL and not self.use_isp
        )
    
    @property
    def use_langgraph_platform(self) -> bool:
        """LangGraph Platformを使用するかどうか"""
        return self.is_production and self.LANGGRAPH_SERVER_URL
    
    @property
    def use_authn_platform(self) -> bool:
        """AuthN Platformを使用するかどうか"""
        return self.is_production and self.AUTHN_PLATFORM_URL
    
    def get_isp_index_alias(self, client_id: Optional[str] = None) -> str:
        """テナント対応のISPインデックスエイリアスを取得"""
        tenant = client_id or self.ISP_TENANT_ID or self.TENANT_ID
        return f"{self.ISP_INDEX_ALIAS}_{tenant}"

    def get_elasticsearch_index(self, index_type: str = "rag") -> str:
        """テナント対応のElasticsearchインデックス名を取得（レガシー）"""
        return f"{self.ELASTICSEARCH_INDEX_PREFIX}-{index_type}-{self.TENANT_ID}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# グローバル設定インスタンス
settings = Settings()

# ディレクトリの作成
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)

