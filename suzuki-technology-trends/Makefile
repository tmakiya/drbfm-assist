.PHONY: help up down restart logs build clean init test

# Docker Composeコマンドを自動検出
DOCKER_COMPOSE := $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; elif docker compose version >/dev/null 2>&1; then echo docker compose; else echo ""; fi)

ifeq ($(DOCKER_COMPOSE),)
$(error Docker Composeが利用できません。Docker Desktopをインストールしてください。詳細: INSTALL_DOCKER.md)
endif

help: ## ヘルプを表示
	@echo "DrawerAI Technology Review System - Makefile"
	@echo ""
	@echo "利用可能なコマンド:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Docker Composeコマンド: $(DOCKER_COMPOSE)"

check-docker: ## Dockerが起動しているか確認
	@if ! docker info >/dev/null 2>&1; then \
		echo "❌ Dockerが起動していません"; \
		echo "   Docker Desktopを起動してください"; \
		exit 1; \
	fi
	@echo "✅ Dockerは起動しています"

up: check-docker ## Docker Composeでサービスを起動
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "✅ サービスを起動しました"
	@echo "  - フロントエンド: http://localhost:3000"
	@echo "  - バックエンドAPI: http://localhost:8000"
	@echo "  - APIドキュメント: http://localhost:8000/docs"
	@echo ""
	@echo "⏳ サービスが完全に起動するまで30-60秒かかります"
	@echo "   状態確認: make status"

down: ## Docker Composeでサービスを停止
	$(DOCKER_COMPOSE) down

restart: check-docker ## サービスを再起動
	$(DOCKER_COMPOSE) restart

logs: check-docker ## ログを表示
	$(DOCKER_COMPOSE) logs -f

logs-backend: check-docker ## バックエンドのログを表示
	$(DOCKER_COMPOSE) logs -f backend

logs-frontend: check-docker ## フロントエンドのログを表示
	$(DOCKER_COMPOSE) logs -f frontend

logs-db: check-docker ## データベースのログを表示
	$(DOCKER_COMPOSE) logs -f db

build: check-docker ## イメージを再ビルド
	$(DOCKER_COMPOSE) build --no-cache

build-backend: check-docker ## バックエンドイメージを再ビルド
	$(DOCKER_COMPOSE) build --no-cache backend

build-frontend: check-docker ## フロントエンドイメージを再ビルド
	$(DOCKER_COMPOSE) build --no-cache frontend

clean: check-docker ## 停止してボリュームも削除（データが消えます）
	$(DOCKER_COMPOSE) down -v
	@echo "⚠️  ボリュームを削除しました"

init: check-docker ## データベースを初期化
	$(DOCKER_COMPOSE) exec backend python scripts/init_db.py

migrate: check-docker ## データベースマイグレーションを実行
	$(DOCKER_COMPOSE) exec backend alembic upgrade head

migrate-create: check-docker ## 新しいマイグレーションを作成
	@read -p "マイグレーションメッセージ: " msg; \
	$(DOCKER_COMPOSE) exec backend alembic revision --autogenerate -m "$$msg"

shell-backend: check-docker ## バックエンドコンテナのシェルに入る
	$(DOCKER_COMPOSE) exec backend bash

shell-frontend: check-docker ## フロントエンドコンテナのシェルに入る
	$(DOCKER_COMPOSE) exec frontend sh

shell-db: check-docker ## データベースに接続
	$(DOCKER_COMPOSE) exec db psql -U drawerai_user -d drawerai

test: check-docker ## テストを実行
	$(DOCKER_COMPOSE) exec backend pytest tests/ -v

ps: check-docker ## サービス状態を表示
	$(DOCKER_COMPOSE) ps

status: check-docker ## サービス状態とヘルスチェックを表示
	@echo "📊 サービス状態:"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "🏥 ヘルスチェック:"
	@curl -s http://localhost:8000/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "⚠️  バックエンドが起動していません（起動中かもしれません）"

