# DRBFM Ingestion Job

Kubernetes Job for extracting, transforming, and loading data for DRBFM assist.

## Quick Links

- [ローカル開発環境での実行](./docs/local-dev-job-execution.md)
- [Kubernetes環境での手動実行](./docs/dev-job-execution.md)
- [新規テナント追加手順](./docs/add-new-tenant.md)

## Quick Start

```bash
# 1. Build Docker image
cd ingestion/
docker build -t asia-northeast1-docker.pkg.dev/zoolake-dev/agent-platform-drbfm-assist-ingestion:latest .
docker push asia-northeast1-docker.pkg.dev/zoolake-dev/agent-platform-drbfm-assist-ingestion:latest

# 2. Apply Kubernetes manifests (managed in zoolake-cluster-config)
cd ../../zoolake-cluster-config/applications/agent-ingestion-infra/overlays/dev/
kubectl apply -k .
```

> **Note**: Kubernetes manifests are managed in the `zoolake-cluster-config` repository under `applications/agent-ingestion-infra/overlays/{env}/`

## Architecture

```
main.py (Entrypoint)
  ↓
tenants/{env}/{tenant_id}/main.py
  ↓
defects/main.py → MSQP → Gemini → ISP
```

## Directory Structure

```
ingestion/
├── main.py                 # Job entrypoint
├── Dockerfile              # Container image
├── pyproject.toml          # Project dependencies
├── docs/                   # Documentation
│   ├── local-dev-job-execution.md # ローカル開発環境での実行手順
│   ├── dev-job-execution.md       # Kubernetes環境での手動実行手順
│   └── add-new-tenant.md          # 新規テナント追加手順
├── common/                 # Shared utilities
│   ├── gcs/               # GCS download client
│   ├── gemini/            # Gemini AI client with Langfuse integration
│   ├── isp/               # ISP API client
│   ├── msqp/              # MSQP (Trino) client
│   ├── m2m_token_issuer/  # M2M Token Issuer client
│   ├── pipelines/         # Shared pipeline components
│   ├── prompts/           # LLM prompt templates
│   ├── path.py            # Path utilities
│   └── setup_local_proxy.sh  # Local development proxy setup
└── tenants/                # Tenant-specific configurations
    ├── dev/
    │   └── a7753ab8.../   # Tenant-specific scripts
    │       ├── main.py    # Tenant orchestrator
    │       └── defects/   # Defect analysis pipeline
    ├── stg/
    └── prod/

# Kubernetes manifests are in zoolake-cluster-config repository:
zoolake-cluster-config/applications/agent-ingestion-infra/
├── base/
│   └── kustomization.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── drbfm-a7753ab8.yaml    # DRBFM ingestion CronJob
    ├── stg/
    └── prod/
```

## Configuration

### Environment Variables

Required environment variables:

**Authentication (Secret)**:
- `MSQP_CLIENT_ID`: OAuth2 client ID for MSQP
- `MSQP_CLIENT_SECRET`: OAuth2 client secret for MSQP
- `M2M_INTERNAL_TOKEN_CLIENT_ID`: M2M Token Issuer client ID for ISP
- `M2M_INTERNAL_TOKEN_CLIENT_SECRET`: M2M Token Issuer client secret for ISP

**Configuration (ConfigMap)**:
- `ENVIRONMENT`: Environment (dev/stg/prod)
- `TENANT_ID`: Tenant identifier
- `LOGURU_LEVEL`: Logging level (default: INFO)

**Optional**:
- `LOCAL_MODE`: Set to `true` for local development (enables SOCKS5 proxy and local ISP)
- `QUERY_FILE_LIMIT`: Limit number of query files to process
- `HTTPS_PROXY`: Proxy for MSQP connection (auto-set in LOCAL_MODE)
- `ISP_API_URL`: ISP API endpoint (auto-set in LOCAL_MODE)

### Kubernetes Resources

Managed in **zoolake-cluster-config** repository under:
```
applications/agent-ingestion-infra/overlays/{env}/
```

Each tenant has a manifest file (e.g., `drbfm-a7753ab8.yaml`) containing:
- ConfigMap: `drbfm-{tenant-id}-ingestion-config`
- ExternalSecret: `drbfm-{tenant-id}-ingestion-secret`
- ServiceAccount: `drbfm-ingestion-{tenant-id}-sa`
- CronJob: `drbfm-ingestion-{tenant-id}` (suspended by default)

Namespace: `agent-ingestion-infra`

## Usage

### Local Development

詳細は [ローカル開発環境での実行手順](./docs/local-dev-job-execution.md) を参照してください。


### Kubernetes Dev Execution

詳細は [Kubernetes環境での手動実行手順](./docs/dev-job-execution.md) を参照してください。


## Monitoring

### Check Job Status

```bash
# List all DRBFM ingestion jobs
kubectl get jobs -n agent-ingestion-infra -l app=drbfm-ingestion

# Get specific job
kubectl get job drbfm-ingestion-a7753ab8 -n agent-ingestion-infra

# Describe job
kubectl describe job drbfm-ingestion-a7753ab8 -n agent-ingestion-infra
```

### View Logs

```bash
# Follow logs
kubectl logs -f job/drbfm-ingestion-a7753ab8 -n agent-ingestion-infra

# Get all logs
kubectl logs job/drbfm-ingestion-a7753ab8 -n agent-ingestion-infra

# Get logs from specific pod
kubectl logs drbfm-ingestion-a7753ab8-xxxxx -n agent-ingestion-infra
```

### Check Pods

```bash
# List pods
kubectl get pods -n agent-ingestion-infra -l app=drbfm-ingestion

# Describe pod
kubectl describe pod drbfm-ingestion-a7753ab8-xxxxx -n agent-ingestion-infra
```

## Adding New Tenants

詳細は [新規テナント追加手順](./docs/add-new-tenant.md) を参照してください。

### Prerequisites

The infrastructure for DRBFM ingestion is managed by Terraform in the `zoolake-infra` repository. Before adding a new tenant, ensure the following infrastructure is in place:

1. **Client Credentials** (MSQP and M2M Token Issuer)
2. **GCP Service Account** (created by Terraform)
3. **Secret Manager Secrets** (created by Terraform, values set manually)
4. **IAM Permissions** (created by Terraform)
5. **Kubernetes Manifests** (in zoolake-cluster-config repository)

### Quick Overview

新規テナントの追加には以下のステップが必要です:

1. **Client申請**: MSQP と M2M Token Issuer の client credentials を取得
2. **Terraform**: `zoolake-infra` リポジトリで Service Account と Secret Manager を作成
3. **Secret設定**: Secret Manager に client secret を設定
4. **Kubernetes Manifest**: `zoolake-cluster-config` リポジトリで CronJob を定義
5. **テナントコード**: `tenants/{env}/{tenant_id}/` ディレクトリにパイプラインコードを作成

詳細な手順は [新規テナント追加手順](./docs/add-new-tenant.md) を参照してください。

## Cleanup

```bash
# Delete specific job
kubectl delete job drbfm-ingestion-a7753ab8 -n agent-ingestion-infra

# Delete all completed jobs
kubectl delete jobs -n agent-ingestion-infra -l app=drbfm-ingestion --field-selector status.successful=1

# Delete all failed jobs
kubectl delete jobs -n agent-ingestion-infra -l app=drbfm-ingestion --field-selector status.failed=1
```

## Troubleshooting

### Job Fails Immediately

Check pod logs and events:
```bash
kubectl logs job/drbfm-ingestion-{tenant-id} -n agent-ingestion-infra
kubectl describe pod drbfm-ingestion-{tenant-id}-xxxxx -n agent-ingestion-infra
```

Common issues:
- Missing or incorrect Secret values
- Invalid tenant ID
- Image pull errors

### Authentication Errors

Verify credentials in GCP Secret Manager:
```bash
gcloud secrets versions access latest \
  --secret=drbfm-ingestion-{tenant-id}-msqp-client-id \
  --project=zoolake-dev
```

### Connection Errors

Ensure running inside Kubernetes cluster with access to internal endpoints:
- `msqp-auth.dp.internal.caddi.io`
- `trino.dp.internal.caddi.io`

## Development


## Common Modules

### GCS Client (`common/gcs/`)

Downloads files from Google Cloud Storage with parallel processing support.

```python
from common.gcs import download_files

success, total = download_files(
    bucket_name="drawer_drawing_images",
    blob_paths=["path/to/file1.png", "path/to/file2.png"],
    local_paths=[Path("data/file1.png"), Path("data/file2.png")],
    max_workers=4,
)
```

### Gemini Client (`common/gemini/`)

Analyze images using Google Gemini with structured output and Langfuse prompt management.

```python
from common.gemini import analyze_images_with_structured_output

result = analyze_images_with_structured_output(
    image_paths=[Path("image1.png"), Path("image2.png")],
    system_instruction="Analyze these technical drawings...",
    response_schema={"type": "object", "properties": {...}},
    model_name="gemini-2.5-flash",
)
```

Features:
- Structured JSON output with schema validation
- Langfuse prompt management integration
- Automatic retry with exponential backoff
- Token usage tracking
- Multi-image analysis in single API call

### MSQP Client (`common/msqp/`)

Query data warehouse (Trino) with OAuth2 authentication.

```python
from common.msqp import create_msqp_client_from_env

client = create_msqp_client_from_env()
client.use(catalog="drawing", schema="msqp__drawing")
df = client.query("SELECT * FROM drawing_png_image LIMIT 10")
```

Supports both local development mode (SOCKS5 proxy) and GKE mode (internal DNS).

### ISP Client (`common/isp/`)

Interactive Search Platform API client for indexing and searching documents.

```python
from common.isp import ISPClient

client = ISPClient.from_env()
client.index_document(index_name="defects", document_id="123", content={...})
```

### M2M Token Issuer (`common/m2m_token_issuer/`)

M2M Token Issuer client for obtaining internal tokens for ISP authentication.

```python
from common.m2m_token_issuer import M2MTokenIssuer

issuer = M2MTokenIssuer.from_env()
token = issuer.get_token()
```

## Tenant-Specific Pipelines

Each tenant has its own directory under `tenants/{env}/{tenant_id}/` with tenant-specific ingestion pipelines.

### Example: Defects Pipeline

End-to-end pipeline for extracting and analyzing defect data:

1. **Extract**: Query defect data from MSQP (Trino)
2. **Transform**: Use Gemini to extract structured attributes from defect descriptions
3. **Load**: Index transformed data to ISP for semantic search

Pipeline structure:
```
tenants/{env}/{tenant_id}/
├── main.py              # Tenant orchestrator (calls all pipelines)
└── defects/
    └── main.py          # Defects pipeline implementation
```

Run locally:
```bash
cd /path/to/drbfm-assist

# Setup local proxies (SOCKS5 + kubectl port-forward)
bash ingestion/common/setup_local_proxy.sh &

# Run specific pipeline
uv run python ingestion/main.py \
  --env dev \
  --tenant-id a7753ab8-12e3-44f0-9ae6-9e85637b890e \
  --pipeline defects
```

## Related Documentation

### Ingestion Documentation
- [ローカル開発環境での実行](./docs/local-dev-job-execution.md)
- [Kubernetes環境での手動実行](./docs/dev-job-execution.md)
- [新規テナント追加手順](./docs/add-new-tenant.md)

### Component Documentation
- [MSQP Client](./common/msqp/)
- [Gemini Client](./common/gemini/)
- [GCS Client](./common/gcs/)
- [ISP Client](./common/isp/)
- [M2M Token Issuer](./common/m2m_token_issuer/)

### External Resources
- [Main Project README](../README.md)
- [Kubernetes Manifests (zoolake-cluster-config)](../../zoolake-cluster-config/applications/agent-ingestion-infra/)
