#!/bin/bash
# Docker Compose動作テストスクリプト

set -e

# Docker Composeコマンドを自動検出
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Composeが利用できません"
    exit 1
fi

echo "🧪 DrawerAI Technology Review System - Docker Compose動作テスト"
echo ""

# サービスが起動しているか確認
if ! $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
    echo "⚠️  サービスが起動していません"
    echo "   先に 'make up' または './scripts/docker-start.sh' を実行してください"
    exit 1
fi

echo "✅ サービスが起動しています"
echo ""

# バックエンドのヘルスチェック
echo "🏥 バックエンドのヘルスチェック..."
if curl -f http://localhost:8000/health &> /dev/null; then
    echo "  ✅ バックエンドは正常に動作しています"
    curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "  (JSON解析スキップ)"
else
    echo "  ❌ バックエンドに接続できません"
    echo "     ログを確認: docker-compose logs backend"
    exit 1
fi
echo ""

# フロントエンドの確認
echo "🌐 フロントエンドの確認..."
if curl -f http://localhost:3000 &> /dev/null; then
    echo "  ✅ フロントエンドは正常に動作しています"
else
    echo "  ⚠️  フロントエンドに接続できません（起動中かもしれません）"
    echo "     ログを確認: docker-compose logs frontend"
fi
echo ""

# データベースの確認
echo "🗄️  データベースの確認..."
if $DOCKER_COMPOSE_CMD exec -T db pg_isready -U drawerai_user -d drawerai &> /dev/null; then
    echo "  ✅ データベースは正常に動作しています"
else
    echo "  ❌ データベースに接続できません"
    exit 1
fi
echo ""

# Redisの確認
echo "🔴 Redisの確認..."
if $DOCKER_COMPOSE_CMD exec -T redis redis-cli ping | grep -q "PONG"; then
    echo "  ✅ Redisは正常に動作しています"
else
    echo "  ❌ Redisに接続できません"
    exit 1
fi
echo ""

echo "✅ 全テスト完了！"
echo ""
echo "🌐 アクセスURL:"
echo "  - フロントエンド: http://localhost:3000"
echo "  - バックエンドAPI: http://localhost:8000"
echo "  - APIドキュメント: http://localhost:8000/docs"

