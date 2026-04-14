"""
マイグレーション作成スクリプト（ヘルパー）
"""
import subprocess
import sys

def create_migration(message: str):
    """マイグレーションを作成"""
    cmd = ["alembic", "revision", "--autogenerate", "-m", message]
    subprocess.run(cmd)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python create_migration.py 'マイグレーションメッセージ'")
        sys.exit(1)
    
    message = sys.argv[1]
    create_migration(message)

