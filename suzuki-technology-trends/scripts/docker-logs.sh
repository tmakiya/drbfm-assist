#!/bin/bash
# Docker Composeログ表示スクリプト

# Docker Composeコマンドを自動検出
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Composeが利用できません"
    exit 1
fi

SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "📋 全サービスのログを表示します"
    echo "   特定のサービスのみ表示: ./scripts/docker-logs.sh backend"
    echo ""
    $DOCKER_COMPOSE_CMD logs -f
else
    echo "📋 $SERVICE のログを表示します"
    echo ""
    $DOCKER_COMPOSE_CMD logs -f $SERVICE
fi

