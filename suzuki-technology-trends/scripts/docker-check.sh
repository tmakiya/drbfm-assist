#!/bin/bash
# Docker Compose設定チェックスクリプト

set -e

echo "🔍 DrawerAI Technology Review System - Docker Compose設定チェック"
echo ""

# Dockerの確認
if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません"
    echo ""
    echo "📥 Docker Desktopのインストール方法:"
    echo "   1. https://www.docker.com/products/docker-desktop/ にアクセス"
    echo "   2. 'Download for Mac'をクリック"
    echo "   3. ダウンロードした.dmgファイルを開く"
    echo "   4. DockerアイコンをApplicationsフォルダにドラッグ"
    echo "   5. ApplicationsからDockerを起動"
    echo "   6. Docker Desktopが起動するまで待つ（メニューバーにDockerアイコンが表示される）"
    echo ""
    echo "   インストール後、このスクリプトを再実行してください"
    exit 1
fi

# Dockerデーモンが起動しているか確認
if ! docker info &> /dev/null; then
    echo "⚠️  Dockerはインストールされていますが、起動していません"
    echo ""
    echo "🚀 Docker Desktopを起動してください:"
    echo "   1. ApplicationsからDockerを起動"
    echo "   2. メニューバーにDockerアイコンが表示されるまで待つ"
    echo "   3. このスクリプトを再実行してください"
    exit 1
fi

# Docker Composeの確認（V1またはV2）
DOCKER_COMPOSE_CMD=""
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Composeが利用できません"
    echo "   Docker Desktopを再インストールしてください"
    exit 1
fi

echo "✅ Docker: $(docker --version)"
if [ "$DOCKER_COMPOSE_CMD" = "docker-compose" ]; then
    echo "✅ Docker Compose: $(docker-compose --version)"
else
    echo "✅ Docker Compose: $(docker compose version)"
fi
echo ""

# .envファイルの確認
if [ ! -f .env ]; then
    echo "⚠️  .envファイルが見つかりません"
    if [ -f .env.example ]; then
        echo "📝 .env.exampleから.envを作成しますか？ (y/n)"
        read -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cp .env.example .env
            echo "✅ .envファイルを作成しました"
            echo "⚠️  必ず.envファイルを編集してGOOGLE_APPLICATION_CREDENTIALSを設定してください"
        fi
    fi
else
    echo "✅ .envファイルが見つかりました"
    
    # GOOGLE_APPLICATION_CREDENTIALSの確認
    if ! grep -q "^GOOGLE_APPLICATION_CREDENTIALS=" .env || grep -q "^GOOGLE_APPLICATION_CREDENTIALS=$" .env; then
        echo "⚠️  GOOGLE_APPLICATION_CREDENTIALSが設定されていません"
        echo "   .envファイルを編集してGOOGLE_APPLICATION_CREDENTIALSを設定してください"
    else
        CREDENTIALS_PATH=$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
        # 相対パスの場合はプロジェクトルートからのパスとして扱う
        if [[ "$CREDENTIALS_PATH" != /* ]]; then
            CREDENTIALS_PATH="$(pwd)/$CREDENTIALS_PATH"
        fi
        if [ -f "$CREDENTIALS_PATH" ]; then
            echo "✅ GOOGLE_APPLICATION_CREDENTIALSが設定されています: $CREDENTIALS_PATH"
        else
            echo "⚠️  GOOGLE_APPLICATION_CREDENTIALSで指定されたファイルが見つかりません: $CREDENTIALS_PATH"
            echo "   ファイルが存在することを確認してください"
        fi
    fi
fi
echo ""

# 必要なディレクトリの確認
echo "📁 ディレクトリ構造の確認:"
required_dirs=("backend" "frontend" "shared")
for dir in "${required_dirs[@]}"; do
    if [ -d "$dir" ]; then
        echo "  ✅ $dir/"
    else
        echo "  ❌ $dir/ が見つかりません"
        exit 1
    fi
done
echo ""

# docker-compose.ymlの確認
if [ -f docker-compose.yml ]; then
    echo "✅ docker-compose.ymlが見つかりました"
else
    echo "❌ docker-compose.ymlが見つかりません"
    exit 1
fi
echo ""

# ポートの確認
echo "🔌 ポートの確認:"
ports=(8000 3000 5432 6379)
for port in "${ports[@]}"; do
    if lsof -i :$port &> /dev/null; then
        echo "  ⚠️  ポート $port は既に使用されています"
        lsof -i :$port | head -2
    else
        echo "  ✅ ポート $port は利用可能です"
    fi
done
echo ""

echo "✅ 設定チェック完了"
echo ""
echo "次のステップ:"
echo "  1. .envファイルを編集してGOOGLE_API_KEYを設定"
echo "  2. ./scripts/docker-start.sh を実行して起動"
echo "  または"
echo "  2. make up を実行して起動"

