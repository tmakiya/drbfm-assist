# 本番デプロイ方向性ドキュメント

## 概要

本ドキュメントは、DrawerAI Technology Review System（スズキ技術トレンド分析システム）を本番環境（GKE）にデプロイするための方向性を定義します。

**作成日:** 2026-01-09
**ステータス:** MVP優先アプローチ

---

## 決定事項サマリー

| 項目 | 決定内容 |
|------|----------|
| 認証 | Internal Token（CADDI内部JWT） |
| 検索バックエンド | Interactive Search Platform (Elasticsearch) |
| ワークフロー実行 | LangGraph Platform (zoolake.jp) |
| データ永続化 | LangGraph Platform（スレッド/ラン管理） |
| UI | Next.js維持、GKEにデプロイ |
| FastAPIバックエンド | **廃止** → UIがLangGraph Platform/ISPと直接連携 |
| ファイルストレージ | 使用しない |
| データ前処理 | ingestionコンテナ（drbfm-assist方式） |
| ログ・モニタリング | LangSmith中心 |
| テナント構成 | シングルテナント（スズキ専用） |
| LangGraph対応方法 | **`langgraph new` + 移植** |

---

## 認証フロー（Internal Token）

### 概要

CADDI内部で発行されるJWT（Internal Token）を使用して認証・認可を行います。
トークンはUI → LangGraph Platform → ISP の全経路でパススルーされます。

### トークンの流れ

```
┌─────────────┐
│  ユーザー   │
└──────┬──────┘
       │ ① ログイン
       ▼
┌─────────────────────┐
│   AuthN Platform    │
│   (認証基盤)        │
└──────┬──────────────┘
       │ ② Internal Token (JWT) 発行
       ▼
┌─────────────────────┐
│   Frontend          │
│   (Next.js)         │
│                     │
│   Authorization:    │
│   Bearer {token}    │
└──────┬──────────────┘
       │ ③ トークンをヘッダーに付与してAPI呼び出し
       ▼
┌─────────────────────┐
│  LangGraph Platform │
│                     │
│  @auth.authenticate │
│  → tenant_id抽出    │
│  → internal_token   │
│    をconfigに保存   │
└──────┬──────────────┘
       │ ④ ワークフローノードからISP呼び出し時にトークンを使用
       ▼
┌─────────────────────┐
│   ISP               │
│   (Elasticsearch)   │
│                     │
│   Authorization:    │
│   Bearer {token}    │
└─────────────────────┘
```

### Internal Token構造

```json
{
  "iss": "https://caddi.internal",
  "sub": "auth0|xxxx",
  "https://zoolake.jp/claims/tenantId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "https://zoolake.jp/claims/email": "user@example.com",
  "exp": 1234567890
}
```

---

## 利用する既存クライアントライブラリ

### LangGraph Platform (TypeScript)

**パッケージ:** [@langchain/langgraph-sdk](https://www.npmjs.com/package/@langchain/langgraph-sdk)

```bash
npm install @langchain/langgraph-sdk
```

```typescript
import { Client } from "@langchain/langgraph-sdk";

// Internal Tokenをヘッダーに設定
const client = new Client({
  apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL,
  defaultHeaders: {
    Authorization: `Bearer ${internalToken}`,
  },
});
```

### Interactive Search Platform (ISP)

#### TypeScriptクライアント（Frontend用）

**パッケージ:** `@caddi/interactive_search_platform_api_client_axios`

#### Pythonクライアント（LangGraph Platform / ingestion用）

**パッケージ:** Artifact Registryで公開（パッケージ名は要確認）

> **TODO:** ISPチームにPythonクライアントのパッケージ名を確認
> Slack: [#4-pj-tech-interactive-search-platform](https://caddijp.slack.com/archives/C08PVLF6WDV)

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│                           GKE Cluster                                │
│  ┌─────────────┐                                                    │
│  │  Frontend   │ @langchain/langgraph-sdk                           │
│  │  (Next.js)  │                                                    │
│  └──────┬──────┘                                                    │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          │ Authorization: Bearer {internal_token}
          ▼
┌─────────────────────┐     ┌─────────────────────┐
│  LangGraph Platform │────▶│      LangSmith      │
│  (zoolake.jp)       │     │   (トレーシング)    │
│                     │     └─────────────────────┘
│  @auth.authenticate │
│  → tenant_id抽出    │
│  → token保存        │
└──────────┬──────────┘
           │
           │ Authorization: Bearer {internal_token}
           ▼
┌─────────────────────┐
│   Interactive       │
│   Search Platform   │
│   (Elasticsearch)   │
└─────────────────────┘
```

---

## LangGraph Platform対応: `langgraph new` + 移植

### 新規プロジェクト構成

```
langgraph/                           # langgraph new で生成
├── suzuki_tech_review/
│   ├── graph.py                     # グラフ定義（エントリポイント）
│   ├── auth.py                      # 認証（drbfm-assistからコピー）
│   ├── config/
│   │   └── experts.py               # 専門家定義（既存からコピー）
│   ├── chains/
│   │   └── tech_review_workflow.py  # ワークフロー実装（移植）
│   └── isp/
│       └── __init__.py              # ISPクライアント（公式パッケージ使用）
├── langgraph.json
├── pyproject.toml
└── Dockerfile
```

### 認証実装（auth.py）

drbfm-assist-prototypeの`backend/drassist/auth.py`をそのままコピーして使用：

```python
# auth.pyの主要な処理

@auth.authenticate
async def authenticate(headers: dict) -> Auth.types.MinimalUserDict:
    """Internal Tokenを検証してユーザー情報を抽出"""
    token = headers.get("authorization", "")[7:]  # "Bearer " 除去

    decoded = jwt.decode(token, options={"verify_signature": False})

    # issuer確認
    if decoded.get("iss") != "https://caddi.internal":
        raise Auth.exceptions.HTTPException(status_code=401)

    return {
        "identity": tenant_id,
        "tenant_id": decoded.get("https://zoolake.jp/claims/tenantId"),
        "user_id": decoded.get("sub"),
        "user_email": decoded.get("https://zoolake.jp/claims/email"),
        "internal_token": token,  # ISP認証用にパススルー
    }

def get_internal_token_from_config(config: RunnableConfig) -> str | None:
    """ワークフローノードからInternal Tokenを取得"""
    auth_user = config.get("configurable", {}).get("langgraph_auth_user", {})
    return auth_user.get("internal_token")
```

### ワークフローノードでのISP呼び出し

```python
# chains/tech_review_workflow.py
from ..auth import get_internal_token_from_config
from caddi_isp_client import ISPClient  # パッケージ名は要確認

def rag_search_node(state: WorkflowState, config: RunnableConfig) -> dict:
    """RAG検索ノード"""
    # Internal Tokenを取得
    internal_token = get_internal_token_from_config(config)

    # ISPクライアントにトークンを設定
    client = ISPClient()
    client.set_internal_token(internal_token)

    # 検索実行
    results = client.search(
        alias="suzuki-tech-trend",
        query=build_query(state.tech_keywords),
        size=10
    )

    return {"rag_results": results["hits"]["hits"]}
```

### langgraph.json

```json
{
  "graphs": {
    "tech-review-workflow": "./suzuki_tech_review/graph.py:graph"
  },
  "auth": {
    "path": "./suzuki_tech_review/auth.py:auth"
  }
}
```

---

## Frontend実装

### LangGraphクライアント

```typescript
// lib/langgraph.ts
import { Client } from "@langchain/langgraph-sdk";

export function getLangGraphClient(internalToken: string) {
  return new Client({
    apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL,
    defaultHeaders: {
      Authorization: `Bearer ${internalToken}`,
    },
  });
}

export async function* runAnalysis(
  internalToken: string,
  input: AnalysisInput
) {
  const client = getLangGraphClient(internalToken);

  // スレッド作成
  const thread = await client.threads.create();

  // ストリーミング実行
  const stream = client.runs.stream(
    thread.thread_id,
    "tech-review-workflow",
    {
      input: {
        topic: input.topic,
        use_case: input.useCase,
        interest_keywords: input.interestKeywords,
        tech_keywords: input.techKeywords,
      },
      streamMode: "values",
    }
  );

  for await (const event of stream) {
    yield event;
  }
}
```

### Internal Token取得（開発時）

```typescript
// 開発時は環境変数から取得
const internalToken = process.env.INTERNAL_TOKEN;

// 本番時はAuthN Platformから取得（実装は要検討）
```

---

## データ前処理（ingestionコンテナ）

### ディレクトリ構成

```
ingestion/
├── main.py
├── tenants/
│   └── prod/
│       └── suzuki/
│           ├── main.py
│           └── config.yaml
├── scripts/
│   └── preprocess/
├── pyproject.toml
└── Dockerfile
```

### ISPへのインデックス登録

```python
# ISP_AUTH_TOKEN環境変数でトークンを設定
client = ISPClient()
client.set_internal_token(os.environ["ISP_AUTH_TOKEN"])

client.bulk_index(alias="suzuki-tech-trend", documents=documents)
```

---

## 環境変数

### Frontend (GKE)

```bash
NEXT_PUBLIC_LANGGRAPH_URL=https://langgraph.zoolake.jp
# 開発時のみ
INTERNAL_TOKEN=<dev-token>
```

### LangGraph Platform

```bash
GOOGLE_API_KEY=<secret>
ISP_URL=https://isp.zoolake.jp
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=suzuki-tech-review
# 開発時のみ
INTERNAL_TOKEN=<dev-token>
```

### Ingestion

```bash
ISP_URL=https://isp.zoolake.jp
ISP_AUTH_TOKEN=<secret>
GOOGLE_API_KEY=<secret>
```

---

## 実装タスク（MVP）

### Phase 1: LangGraph Platform新規作成

1. [ ] ISPチームにPythonクライアントのパッケージ名を確認
2. [ ] `langgraph new suzuki-tech-review` で雛形作成
3. [ ] `auth.py` をdrbfm-assist-prototypeからコピー
4. [ ] `experts.py` をコピー
5. [ ] `WorkflowState` を移植
6. [ ] 分析ノードロジック（Turn1/Turn2）を移植
7. [ ] ISP連携でRAG検索を実装（`get_internal_token_from_config`使用）
8. [ ] ローカルテスト（`langgraph dev`、`INTERNAL_TOKEN`環境変数使用）
9. [ ] LangSmith (zoolake.jp) にデプロイ

### Phase 2: Frontend対応

10. [ ] `@langchain/langgraph-sdk` インストール
11. [ ] LangGraph Platformクライアント実装（Internal Token対応）
12. [ ] 分析画面のAPI呼び出し変更
13. [ ] Dockerfile本番化
14. [ ] GKEデプロイ設定作成

### Phase 3: データ前処理

15. [ ] ingestionディレクトリ構成作成
16. [ ] CSVパイプライン実装
17. [ ] ISPインデックス作成・データ投入

### Phase 4: クリーンアップ

18. [ ] 不要なバックエンドコード削除
19. [ ] docker-compose.yml整理
20. [ ] ドキュメント更新

---

## 確認事項（TODO）

- [ ] ISP Pythonクライアントのパッケージ名を確認
- [ ] ISPのインデックス命名規則を確認
- [ ] LangSmithデプロイ手順を確認（drbfm-assistチームに相談）
- [ ] FrontendでのInternal Token取得方法を確認

---

## 参考資料

- [drbfm-assist-prototype](https://github.com/caddijp/drbfm-assist-prototype): ISP/LangGraph/AuthN連携の実装例
  - 特に `backend/drassist/auth.py` と `ui/src/client.py`
- [interactive-search-platform](https://github.com/caddijp/interactive-search-platform): ISP APIドキュメント
- [@langchain/langgraph-sdk (npm)](https://www.npmjs.com/package/@langchain/langgraph-sdk): TypeScript SDK
- [LangGraph Platform Docs](https://langchain-ai.github.io/langgraph/cloud/): 公式ドキュメント

---

## 次のステップ

1. 本ドキュメントの内容を関係者とレビュー
2. ISPチームにPythonクライアントのパッケージ名を確認
3. `langgraph new suzuki-tech-review` でプロジェクト作成
4. drbfm-assist-prototypeから`auth.py`をコピー
5. 既存コードから専門家定義・ワークフローロジックを移植
