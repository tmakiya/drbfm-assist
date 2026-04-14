# DrawerAI Technology Review System - リポジトリ全体像レポート

## 概要

このプロジェクトは **DrawerAI Technology Review System** という名称で、Google Generative AI（Gemini）を活用したドキュメント分析・RAG（Retrieval-Augmented Generation）システムです。

---

## アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│    Frontend     │     Backend     │    Database     │   Cache   │
│   (Next.js)     │   (FastAPI)     │  (PostgreSQL)   │  (Redis)  │
│   Port: 3000    │   Port: 8000    │   Port: 5432    │ Port:6379 │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
```

---

## ディレクトリ構造

```
solution-suzuki-technology-trend/
├── backend/                  # FastAPI バックエンド
│   ├── app/
│   │   ├── api/endpoints/    # REST API エンドポイント
│   │   │   ├── auth.py       # 認証API
│   │   │   ├── files.py      # ファイル操作API
│   │   │   ├── analysis.py   # 分析API
│   │   │   └── rag.py        # RAG API
│   │   ├── core/             # コアロジック
│   │   │   ├── rag_system.py       # RAGシステム
│   │   │   ├── agents.py           # AIエージェント
│   │   │   ├── langgraph_workflow.py # LangGraphワークフロー
│   │   │   └── search_backend.py   # 検索バックエンド
│   │   ├── db/               # データベース層
│   │   │   ├── models.py     # SQLAlchemyモデル
│   │   │   └── database.py   # DB接続
│   │   ├── services/         # ビジネスロジック
│   │   │   ├── auth_service.py
│   │   │   └── rag_service.py
│   │   ├── middleware/       # セキュリティミドルウェア
│   │   └── utils/            # ユーティリティ
│   ├── alembic/              # DBマイグレーション
│   ├── tests/                # テストコード
│   └── scripts/              # 管理スクリプト
├── frontend/                 # Next.js フロントエンド
│   └── src/
│       ├── pages/
│       │   ├── index.tsx         # トップページ
│       │   ├── login.tsx         # ログイン
│       │   └── analysis/         # 分析ページ
│       ├── components/           # Reactコンポーネント
│       └── lib/api.ts            # APIクライアント
├── shared/                   # 共有コード・スキーマ
├── docs/                     # ドキュメント
├── scripts/                  # 運用スクリプト
├── docker-compose.yml        # 開発環境
├── docker-compose.production.yml # 本番環境
└── Makefile                  # タスクランナー
```

---

## 技術スタック

### バックエンド (Python)

| カテゴリ | 技術 |
|---------|------|
| フレームワーク | FastAPI |
| データベース | PostgreSQL + SQLAlchemy + Alembic |
| キャッシュ/キュー | Redis + Celery |
| AI/LLM | Google Generative AI (Gemini) |
| RAG/ワークフロー | LangChain, LangGraph |
| 検索 | Elasticsearch, FAISS |
| PDF処理 | PyMuPDF |
| OCR | pytesseract, Pillow |

### フロントエンド (TypeScript)

| カテゴリ | 技術 |
|---------|------|
| フレームワーク | Next.js 14 |
| 状態管理 | Zustand |
| スタイリング | Tailwind CSS |
| HTTPクライアント | Axios |
| マークダウン | react-markdown |

### インフラ

| カテゴリ | 技術 |
|---------|------|
| コンテナ | Docker, Docker Compose |
| DB | PostgreSQL 15 |
| キャッシュ | Redis 7 |

---

## 主要機能

1. **認証システム** - JWT認証、ユーザー管理
2. **ファイルアップロード** - PDF等のドキュメントアップロード
3. **RAG検索** - ベクトル検索による知識ベース
4. **AI分析** - Geminiを使用した文書分析
5. **ワークフロー** - LangGraphによるAIエージェントワークフロー

---

## 開発コマンド (Makefile)

| コマンド | 説明 |
|---------|------|
| `make up` | サービス起動 |
| `make down` | サービス停止 |
| `make logs` | ログ表示 |
| `make build` | イメージ再ビルド |
| `make migrate` | DBマイグレーション |
| `make test` | テスト実行 |
| `make shell-backend` | バックエンドシェル |

---

## エンドポイント

| URL | 説明 |
|-----|------|
| http://localhost:3000 | フロントエンド |
| http://localhost:8000 | バックエンドAPI |
| http://localhost:8000/docs | Swagger UI (API仕様) |

---

## 環境変数 (.env.example)

主要な設定項目:
- `SECRET_KEY` - アプリケーションシークレット
- `DATABASE_URL` - PostgreSQL接続URL
- `REDIS_URL` - Redis接続URL
- `LLM_MODEL_NAME_FLASH` - Geminiモデル名
- `GOOGLE_APPLICATION_CREDENTIALS` - GCP認証情報パス
