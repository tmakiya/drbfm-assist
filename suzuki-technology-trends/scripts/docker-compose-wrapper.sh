#!/bin/bash
# Docker Composeコマンドのラッパー（V1/V2対応）

# Docker Composeコマンドを自動検出
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Composeが利用できません"
    echo "   Docker Desktopをインストールしてください"
    exit 1
fi

# 引数をそのまま渡す
exec $DOCKER_COMPOSE_CMD "$@"

