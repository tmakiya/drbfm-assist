# PFMEA AI Workflow Application

P-FMEA (Process Failure Mode and Effects Analysis) AI支援ワークフローアプリケーション。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend Container                            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Streamlit App (frontend/)                                  ││
│  │  - ファイルアップロード・バリデーション                      ││
│  │  - BOP差分解析                                              ││
│  │  - PFMEAマッチング                                          ││
│  │  - LangGraph Client (Backend呼び出し)                       ││
│  │  - 結果表示・Excel出力                                      ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST (langgraph-sdk)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend Container                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  LangGraph Server (backend/)                                ││
│  │  - PFMEA機能マッピングワークフロー                          ││
│  │  - AI推定ワークフロー                                       ││
│  │  - リスク評価ワークフロー (S/O/D)                           ││
│  │  - Vertex AI / Gemini 呼び出し                              ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## ディレクトリ構成

```
denso_pfmea/
├── docker-compose.dev.yml  # Docker Compose 開発構成
├── README.md               # このファイル
├── frontend/               # Streamlit Frontend
│   ├── Dockerfile
│   ├── Makefile
│   ├── pyproject.toml
│   ├── .env.example
│   ├── config/             # 設定ファイル
│   │   ├── bop_rules.yaml
│   │   └── pfmea_ratings.yaml
│   └── src/
│       ├── app.py          # エントリポイント
│       ├── config.py       # 設定クラス
│       ├── client.py       # LangGraph Client
│       ├── common/         # 共通ユーティリティ
│       │   ├── bop/        # BOP解析
│       │   └── pfmea/      # PFMEA解析
│       ├── services/       # ビジネスロジック
│       │   ├── change_pipeline/  # 変更解析パイプライン
│       │   ├── datasets/   # データセット管理
│       │   └── pfmea/      # PFMEAマッピング
│       └── ui/             # UI層
│           ├── components/ # UIコンポーネント
│           ├── design_system/  # デザインシステム
│           ├── pages/      # ページ定義
│           └── state/      # 状態管理
└── backend/                # LangGraph Backend
    ├── langgraph.json      # LangGraph設定
    ├── langgraph-dev.json  # 開発用設定
    ├── Makefile
    ├── pyproject.toml
    ├── .env.example
    ├── config/
    │   ├── bop_rules.yaml
    │   ├── pfmea_ratings.yaml
    │   └── prompts/        # プロンプトテンプレート
    │       ├── pfmea_assessment.md
    │       ├── pfmea_function_mapping.md
    │       └── pfmea_risk_rating.md
    └── src/
        ├── agent/          # LangGraph ワークフロー
        │   ├── graph.py    # グラフ定義
        │   ├── nodes.py    # ワークフローノード
        │   ├── state.py    # State定義
        │   ├── llm_result_parser.py
        │   └── risk_rating_builder.py
        ├── llm/            # LLMクライアント
        │   └── gemini_client.py
        ├── services/       # LLM関連サービス
        │   ├── pfmea/      # PFMEA機能マッピング、リスク評価
        │   ├── circuit_breaker/  # サーキットブレーカー
        │   ├── llm_batch_runner.py
        │   ├── llm_executor.py
        │   └── llm_gateway.py
        └── common/         # 共通ユーティリティ
            ├── bop/        # BOP解析
            └── pfmea/      # PFMEA解析
```

## 開発

### ローカル開発 (推奨構成)

Backend をホスト側で実行し、Frontend を Docker で実行する構成です。

**ターミナル1: Backend (ホスト側)**
```bash
cd denso_pfmea/backend
uv sync
uv run langgraph dev --host 0.0.0.0 --port 8124
```

**ターミナル2: Frontend (Docker)**
```bash
cd denso_pfmea
docker compose -f docker-compose.dev.yml up --build
```

**アクセス:**
- Frontend: http://localhost:8501
- Backend: http://localhost:8124

## ワークフロー

LangGraph ワークフローは以下のノードで構成されています:

1. **prefetch_mappings**: PFMEA機能マッピングの準備
2. **assessment**: AI推定の実行 (Gemini)
3. **risk_rating**: リスク評価 (S/O/D) の実行
4. **aggregate**: 結果の集約
