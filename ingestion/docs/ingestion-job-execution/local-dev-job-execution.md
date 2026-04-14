# ローカル開発環境でのingestionスクリプト実行手順

このドキュメントでは、ローカル環境でingestionスクリプトを実行する方法を説明します。

## 前提条件

- Python 3.13以上がインストールされていること
- `uv` コマンドがインストールされていること
- MSQP/ISPへのアクセス権限があること

## セットアップ

### 1. 依存パッケージのインストール

プロジェクトルートで依存関係をインストールします:

```bash
cd /home/morioka/work/agent/drbfm-assist
uv sync
```

### 2. 環境変数の設定

`.env` ファイルを作成して必要な環境変数を設定します:

```bash
cd ingestion/
cp .env.sample .env
```

`.env` ファイルを編集して以下の値を設定してください:

```bash
# 必須: 環境とテナントID
ENVIRONMENT=dev
TENANT_ID=a7753ab8-12e3-44f0-9ae6-9e85637b890e

# 必須: MSQP認証情報
MSQP_CLIENT_ID=your-client-id
MSQP_CLIENT_SECRET=your-client-secret

# 必須: M2M Token Issuer認証情報（ISP用）
M2M_INTERNAL_TOKEN_CLIENT_ID=your-client-id
M2M_INTERNAL_TOKEN_CLIENT_SECRET=your-client-secret

# ローカル開発モード（SOCKS5プロキシとローカルISPを使用）
LOCAL_MODE=true

# Optional: 設定
QUERY_FILE_LIMIT=2        # 処理するクエリファイル数の制限
LOGURU_LEVEL=INFO         # ログレベル
```

**重要**: `LOCAL_MODE=true` に設定すると、以下が自動的に設定されます:
- MSQPへの接続: `HTTPS_PROXY=socks5h://localhost:1080`
- ISP APIへの接続: `ISP_API_URL=http://localhost:3000`

### 3. ローカルプロキシのセットアップ

ローカル開発モードでは、MSQPとISPへ接続するためにプロキシが必要です。
setup_local_proxy.shスクリプトを使用してプロキシを起動します:

```bash
# SOCKS5プロキシとkubectl port-forwardを起動
cd {PATH_TO_REPO}/drbfm-assist/ingestion/common
./setup_local_proxy.sh
```

このスクリプトは以下を実行します:
- SOCKS5プロキシをポート1080で起動（MSQP接続用）
- kubectl port-forwardでISP APIをポート3000に転送

## 実行方法

### 基本的な実行

ingestion dir から実行します:

```bash
cd {PATH_TO_REPO}/drbfm-assist/ingestion

# 基本実行
uv run python main.py --env $ENV --tenant-id $TENANT_ID
```

### 検証のみ実行（Dry Run）

ISPへの登録は行わず、処理の検証のみを行う場合:

```bash
uv run python main.py --env $ENV --tenant-id $TENANT_ID --dry-run
```

### 特定のパイプラインのみ実行

特定のパイプライン（例: defects）のみ実行する場合:

```bash
uv run python main.py --env $ENV --tenant-id $TENANT_ID --pipeline defects
```

## tenant dir で直接実行

tenant dir で main.pyを直接実行することもできます:

```bash
cd {PATH_TO_REPO}/drbfm-assist/ingestion/tenants/dev/a7753ab8-12e3-44f0-9ae6-9e85637b890e/defects
uv run python main.py
```

## トラブルシューティング

### MSQP接続エラー

```
Error: Failed to connect to MSQP
```

対処法:
1. SOCKS5プロキシが起動しているか確認: `ps aux | grep ssh`
2. `.env` で `LOCAL_MODE=true` が設定されているか確認
3. `MSQP_CLIENT_ID` と `MSQP_CLIENT_SECRET` が正しいか確認


### 環境変数が見つからない

```
Error: Missing environment variables: MSQP_CLIENT_ID
```

対処法:
1. `.env` ファイルが `ingestion/` ディレクトリに存在するか確認
2. 必須の環境変数がすべて設定されているか確認

## 参考情報

- 詳細なアーキテクチャ: [README.md](../README.md)
- Kubernetes環境での手動実行: [manual-execution.md](./manual-execution.md)
