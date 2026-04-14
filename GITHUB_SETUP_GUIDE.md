# GitHub 連携セットアップガイド

## 完了した設定

✅ GitHub リポジトリを作成しました  
✅ リモートを設定しました  
✅ 初期コミットをプッシュしました

**リポジトリ URL**: https://github.com/tmakiya/drbfm-assist

## 開発ワークフロー

### 1. ローカル開発

```bash
# プロジェクトディレクトリに移動
cd /Users/makiyama/Documents/drbfm-assist-main

# 依存関係をインストール
uv sync

# 新しいブランチを作成して開発
git checkout -b feature/your-feature-name

# コード品質チェック
cd backend
uv run ruff check .
uv run ruff format .
pre-commit run --all-files

# テストを実行
uv run pytest tests/

# ファイルをステージして コミット
git add .
git commit -m "feat: describe your changes"

# GitHub にプッシュ
git push origin feature/your-feature-name
```

### 2. プルリクエストの作成

```bash
# GitHub CLI で PR を作成
gh pr create --title "Your PR Title" --body "PR Description"

# または https://github.com/tmakiya/drbfm-assist/pulls で作成
```

### 3. Code Review と マージ

- CI/CD チェックが自動的に実行されます
- レビューを受けてフィードバックに対応します
- approve を受けたら merge します

## 環境変数の設定

### ローカル開発環境

`.env.sample` をコピーして `.env` ファイルを作成します。

```bash
cp .env.sample .env
```

`.env` ファイルに以下の認証情報を設定します：

```env
# Google Cloud (Vertex AI)
GOOGLE_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=

# Azure OpenAI (Embeddings)
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT=

# Elasticsearch
ELASTICSEARCH_URL=

# Langfuse
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
```

**重要**: `.env` ファイルは `.gitignore` で除外されているため、GitHub にアップロードされません。

### GitHub Actions Secrets

CI/CD ワークフローを実行するために、GitHub リポジトリの以下の場所にシークレットを設定します：

**設定場所**: Repository -> Settings -> Secrets and variables -> Actions

必要なシークレット：

#### GCP 認証
- `GCP_PROJECT_ID`: GCP プロジェクト ID
- `GCP_WI_PROVIDER`: Workload Identity Provider ID  
- `GCP_WI_SERVICE_ACCOUNT`: Workload Identity サービスアカウント

#### コンテナレジストリ認証
- `REGISTRY_USERNAME`: Docker レジストリユーザー名
- `REGISTRY_PASSWORD`: Docker レジストリパスワード

#### API キー
- `GOOGLE_CREDENTIALS`: Google Cloud 認証情報（JSON 形式）
- `AZURE_OPENAI_API_KEY`: Azure OpenAI API キー

設定手順：

```bash
# GitHub CLI で シークレットを設定
gh secret set GCP_PROJECT_ID --body "your-project-id"
gh secret set GCP_WI_PROVIDER --body "your-provider"
gh secret set GCP_WI_SERVICE_ACCOUNT --body "your-service-account"

# または GitHub Web UI で設定
# https://github.com/tmakiya/drbfm-assist/settings/secrets/actions
```

## CI/CD パイプライン

### 既存のワークフロー

#### 1. DRBFM Assist CI/CD (`ci-cd-drbfm-assist.yml`)
- コード品質チェック（Ruff、Pre-commit）
- バックエンド テストとビルド
- コンテナ イメージのプッシュ（main ブランチのみ）

#### 2. その他のワークフロー

詳細は `.github/workflows/` ディレクトリを参照してください。

### ワークフローのトリガー

| ワークフロー | トリガー | ブランチ |
|-------------|---------|---------|
| CI/CD | push, pull_request | main, develop |
| Backend Build | push | - |
| Deploy | push | main |

## コミットメッセージの規約

Conventional Commits を使用しています：

```
<type>(<scope>): <subject>

<body>

<footer>
```

タイプ：
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: コード スタイル変更
- `refactor`: コード リファクタリング
- `test`: テスト追加・修正
- `chore`: ビルド・依存関係の変更

例：

```
feat(elasticsearch): add fuzzy search support

- Implement fuzzy matching for search queries
- Support configurable fuzziness levels
- Add unit tests for fuzzy search

Closes #42
```

## ブランチ戦略

- `main`: 本番環境用、常にデプロイ可能な状態
- `develop`: 開発ブランチ
- `feature/*`: 機能開発用のトピック ブランチ
- `fix/*`: バグ修正用のトピック ブランチ
- `hotfix/*`: 緊急修正用のブランチ

## トラブルシューティング

### Push が失敗する場合

```bash
# リモートの最新情報を取得
git fetch origin

# main ブランチを更新（必要に応じて）
git pull origin main

# 再度プッシュ
git push origin feature/your-feature
```

### コンフリクトが発生した場合

```bash
# コンフリクトを確認
git status

# コンフリクトファイルを編集して解決

# 解決済みファイルをステージ
git add <resolved-file>

# コミット
git commit -m "Resolve merge conflicts"

# プッシュ
git push origin feature/your-feature
```

## 参考リンク

- [GitHub リポジトリ](https://github.com/tmakiya/drbfm-assist)
- [プロジェクト管理](https://github.com/tmakiya/drbfm-assist/projects)
- [Issue トラッキング](https://github.com/tmakiya/drbfm-assist/issues)
- [Discussions](https://github.com/tmakiya/drbfm-assist/discussions)

## さらに詳しい情報

詳細は [GITHUB_INTEGRATION.md](./GITHUB_INTEGRATION.md) を参照してください。
