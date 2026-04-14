#!/bin/bash
# Docker Compose停止スクリプト

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

echo "🛑 DrawerAI Technology Review System - Docker Compose停止スクリプト"
echo ""

read -p "サービスを停止しますか？ (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    $DOCKER_COMPOSE_CMD down
    echo ""
    echo "✅ サービスを停止しました"
else
    echo "❌ キャンセルしました"
    exit 0
fi

echo ""
read -p "ボリュームも削除しますか？（データが消えます） (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    $DOCKER_COMPOSE_CMD down -v
    echo "✅ ボリュームも削除しました"
else
    echo "ℹ️  ボリュームは保持されました"
fi

