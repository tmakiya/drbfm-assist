"""
データベース初期化スクリプト
"""
import sys
import os
# sharedモジュールのパスを追加
shared_paths = [
    "/app/shared",  # Dockerコンテナ内
    os.path.join(os.path.dirname(__file__), "../../shared"),  # 開発環境
]
for shared_path in shared_paths:
    if os.path.exists(shared_path) and shared_path not in sys.path:
        sys.path.insert(0, shared_path)
        break
# アプリケーションディレクトリのパスを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.database import engine, Base
from app.db.models import User, Project, Document, AnalysisResult
from app.services.auth_service import create_user
from app.db.database import SessionLocal

def init_db():
    """データベースを初期化"""
    # テーブルを作成
    Base.metadata.create_all(bind=engine)
    print("✅ データベーステーブルを作成しました")
    
    # 初期ユーザーを作成（オプション）
    db = SessionLocal()
    try:
        # テストユーザーが存在しない場合のみ作成
        from app.services.auth_service import get_user_by_username
        if not get_user_by_username(db, "admin"):
            create_user(
                db=db,
                username="admin",
                email="admin@example.com",
                password="admin123",
                client_id="admin"
            )
            print("✅ 初期ユーザー（admin）を作成しました")
        else:
            print("ℹ️  初期ユーザーは既に存在します")
    except Exception as e:
        print(f"⚠️  初期ユーザーの作成に失敗: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()

