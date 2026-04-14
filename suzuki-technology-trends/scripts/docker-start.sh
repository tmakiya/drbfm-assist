#!/bin/bash
# Docker Compose起動スクリプト

set -e

# Docker Composeコマンドを自動検出
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Composeが利用できません"
    echo "   Docker Desktopをインストールしてください"
    echo "   詳細: INSTALL_DOCKER.md を参照してください"
    exit 1
fi

echo "🚀 DrawerAI Technology Review System - Docker Compose起動スクリプト"
echo ""

# Dockerが起動しているか確認
if ! docker info &> /dev/null; then
    echo "⚠️  Dockerが起動していません"
    echo ""
    echo "🚀 Docker Desktopを起動してください:"
    echo "   1. ApplicationsからDockerを起動"
    echo "   2. メニューバーにDockerアイコンが表示されるまで待つ"
    echo "   3. このスクリプトを再実行してください"
    echo ""
    echo "   詳細: INSTALL_DOCKER.md を参照してください"
    exit 1
fi

# .envファイルの確認
if [ ! -f .env ]; then
    echo "⚠️  .envファイルが見つかりません"
    echo "📝 .env.exampleをコピーして.envファイルを作成してください"
    echo ""
    read -p ".env.exampleから.envを作成しますか？ (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env.example .env
        echo "✅ .envファイルを作成しました"
        echo "⚠️  必ず.envファイルを編集してGOOGLE_APPLICATION_CREDENTIALSを設定してください"
        echo ""
        echo "   編集方法:"
        echo "   code .env"
        echo "   または"
        echo "   vi .env"
        echo ""
        echo "   例: GOOGLE_APPLICATION_CREDENTIALS=./caddi-cp-it-gemini-internal-2e058b90ed99.json"
        echo ""
    else
        echo "❌ .envファイルが必要です。終了します。"
        exit 1
    fi
fi

# GOOGLE_APPLICATION_CREDENTIALSの確認
if ! grep -q "^GOOGLE_APPLICATION_CREDENTIALS=" .env || grep -q "^GOOGLE_APPLICATION_CREDENTIALS=$" .env; then
    echo "⚠️  GOOGLE_APPLICATION_CREDENTIALSが設定されていません"
    echo "⚠️  .envファイルを編集してGOOGLE_APPLICATION_CREDENTIALSを設定してください"
    echo ""
    echo "   編集方法:"
    echo "   code .env"
    echo "   または"
    echo "   vi .env"
    echo ""
    echo "   例: GOOGLE_APPLICATION_CREDENTIALS=./caddi-cp-it-gemini-internal-2e058b90ed99.json"
    echo ""
    read -p "続行しますか？（GOOGLE_APPLICATION_CREDENTIALSなしでは一部機能が動作しません） (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 終了します。"
        exit 1
    fi
else
    CREDENTIALS_PATH=$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    # 相対パスの場合はプロジェクトルートからのパスとして扱う
    if [[ "$CREDENTIALS_PATH" != /* ]]; then
        CREDENTIALS_PATH="$(pwd)/$CREDENTIALS_PATH"
    fi
    if [ ! -f "$CREDENTIALS_PATH" ]; then
        echo "⚠️  GOOGLE_APPLICATION_CREDENTIALSで指定されたファイルが見つかりません: $CREDENTIALS_PATH"
        echo "   ファイルが存在することを確認してください"
        echo ""
        read -p "続行しますか？ (y/n): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ 終了します。"
            exit 1
        fi
    fi
fi

echo "📦 Docker Composeでサービスを起動します..."
echo ""

# Docker Compose起動
$DOCKER_COMPOSE_CMD up -d

echo ""
echo "⏳ サービスが起動するまで待機中..."
sleep 10

echo ""
echo "📊 サービス状態:"
docker-compose ps

echo ""
echo "✅ 起動完了！"
echo ""
echo "🌐 アクセスURL:"
echo "  - フロントエンド: http://localhost:3000"
echo "  - バックエンドAPI: http://localhost:8000"
echo "  - APIドキュメント: http://localhost:8000/docs"
echo ""
echo "📝 ログを確認:"
echo "  docker-compose logs -f"
echo ""
echo "🛑 停止:"
echo "  docker-compose down"
echo ""

