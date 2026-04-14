# 本番環境設定ガイド

このドキュメントでは、DrawerAI Technology Review Systemを本番環境にデプロイする際の設定について説明します。

## 環境変数設定

以下の環境変数を`.env.production`ファイルまたはKubernetesのSecretとして設定してください。

### 基本設定

```bash
# 環境設定
ENVIRONMENT=production
TENANT_ID=your-tenant-id
APP_NAME=drawer-ai-tech-review
```

### セキュリティ設定

```bash
SECRET_KEY=your-very-secure-secret-key-change-this-in-production
```

### AuthN Platform設定（Drawer認証連携）

```bash
AUTHN_PLATFORM_URL=https://authn.your-domain.com
AUTHN_INTERNAL_TOKEN=your-internal-token
```

### LLM設定（Google Generative AI）

```bash
GOOGLE_API_KEY=your-google-api-key
LLM_MODEL_NAME_FLASH=gemini-2.5-flash
EMBEDDING_MODEL=models/embedding-001
```

### LangGraph Platform / LangSmith設定

```bash
LANGGRAPH_SERVER_URL=https://langgraph.your-domain.com
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=drawer-ai-tech-review
LANGSMITH_ENDPOINT=https://langsmith.zoolake.jp
WORKFLOW_NAME=tech-review-workflow
```

### Search Platform（Elasticsearch）設定

```bash
SEARCH_BACKEND=elasticsearch
ELASTICSEARCH_URL=https://elasticsearch.your-domain.com
ELASTICSEARCH_API_KEY=your-elasticsearch-api-key
ELASTICSEARCH_INDEX_PREFIX=drawer-ai
```

### データソース設定（MSQP / Catalyst）

```bash
MSQP_ENDPOINT=https://msqp.your-domain.com
CATALYST_ENDPOINT=https://catalyst.your-domain.com
```

### データベース・Redis設定

```bash
DATABASE_URL=postgresql://user:password@db-host:5432/drawerai
REDIS_URL=redis://redis-host:6379/0
```

### CORS・ロギング設定

```bash
CORS_ORIGINS=https://your-frontend-domain.com,https://app.your-domain.com
LOG_LEVEL=INFO
```

## アーキテクチャ概要

本番環境では以下のコンポーネントと連携します：

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Users                                        │
│                           │                                          │
│              /alpha-agents/<tenant_id>/<app_name>                   │
│                           ▼                                          │
├─────────────────────────────────────────────────────────────────────┤
│  AuthN Platform          Agent UI Infrastructure (AURA)             │
│  ┌─────────────┐         ┌────────────────────────────────┐        │
│  │   Drawer    │◄────────│  UI for <app_name>             │        │
│  │   認証基盤   │         │  of <tenant_id>                │        │
│  └─────────────┘         └────────────────────────────────┘        │
│                                      │                               │
│                              Internal token                          │
│                                      ▼                               │
├─────────────────────────────────────────────────────────────────────┤
│  LangGraph Platform                  LangSmith                       │
│  ┌────────────────────────┐         ┌─────────────────────┐        │
│  │  Graph for             │◄────────│  Deployment管理     │        │
│  │  <workflow_name>       │         │  langsmith.zoolake.jp│       │
│  │  of <tenant_id>        │         └─────────────────────┘        │
│  └────────────────────────┘                                         │
│           │                                                          │
│           │ Search                                                   │
│           ▼                                                          │
├─────────────────────────────────────────────────────────────────────┤
│  Search Platform                                                     │
│  ┌────────────────────────────────────────────────────────┐        │
│  │  <index_name> of <tenant_id>                           │        │
│  │  Elasticsearch                                          │        │
│  └────────────────────────────────────────────────────────┘        │
│           ▲                                                          │
│           │ Ingest                                                   │
│           │                                                          │
├─────────────────────────────────────────────────────────────────────┤
│  Data Processing & Ingestion                                         │
│  ┌──────────────┐    ┌──────────────┐                               │
│  │    MSQP      │    │   Catalyst   │                               │
│  │ (structured) │    │(unstructured)│                               │
│  └──────────────┘    └──────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

## 重要な注意事項

1. **認証**: 本番環境ではAuthN Platformを使用します。Agent AppユーザーはDrawerアカウントが必要です。

2. **データアクセス**: 
   - UIはLangGraph Platformのみと通信
   - Graphが実行するデータ操作はShort-term memory + Elasticsearch Queryのみ
   - 外部ストレージへのWriteは不可

3. **マルチテナント**: すべてのリソースは`<tenant_id>`で分離されます。

## デプロイ手順

### 1. LangGraph Platformへのデプロイ

```bash
# LangGraph設定ファイルを生成
python -c "
from backend.app.core.langgraph_platform import generate_langgraph_deployment_config
import json
print(json.dumps(generate_langgraph_deployment_config(), indent=2))
" > langgraph.json

# LangSmithにデプロイ
langgraph deploy --config langgraph.json
```

### 2. Kubernetesへのデプロイ

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: drawer-ai-backend
spec:
  template:
    spec:
      containers:
      - name: backend
        image: drawer-ai-backend:latest
        envFrom:
        - secretRef:
            name: drawer-ai-secrets
```

### 3. Elasticsearchインデックスの設定

Data Processing & Ingestionサービスを使用して、DrawerのデータをElasticsearchにインジェストしてください。

