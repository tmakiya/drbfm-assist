#!/bin/bash
# Docker Composeリセットスクリプト（開発環境用）

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

echo "🔄 DrawerAI Technology Review System - Docker Composeリセット"
echo ""
echo "⚠️  この操作は以下を実行します:"
echo "  - 全サービスを停止"
echo "  - コンテナを削除"
echo "  - ボリュームを削除（データが消えます）"
echo "  - イメージを削除（オプション）"
echo ""

read -p "続行しますか？ (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ キャンセルしました"
    exit 0
fi

echo ""
echo "🛑 サービスを停止中..."
$DOCKER_COMPOSE_CMD down -v

echo ""
read -p "Dockerイメージも削除しますか？ (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  イメージを削除中..."
    $DOCKER_COMPOSE_CMD down --rmi all -v || true
    echo "✅ イメージを削除しました"
fi

echo ""
echo "✅ リセット完了"
echo ""
echo "再起動するには:"
echo "  ./scripts/docker-start.sh"
echo "  または"
echo "  make up"

