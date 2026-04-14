# DRBFM Assist - GitHub 連携開発ガイド

## 📋 目次

1. [クイックスタート](#クイックスタート)
2. [初期セットアップ](#初期セットアップ)
3. [開発ワークフロー](#開発ワークフロー)
4. [GitHub 連携](#github-連携)
5. [環境設定](#環境設定)
6. [CI/CD パイプライン](#cicd-パイプライン)
7. [トラブルシューティング](#トラブルシューティング)

## 🚀 クイックスタート

### 前提条件

- Python 3.10+
- Git
- GitHub CLI (gh)
- Docker & Docker Compose (オプション)
- macOS, Linux, または WSL2 on Windows

### 5分でセットアップ

```bash
# 1. リポジトリをクローン
git clone https://github.com/tmakiya/drbfm-assist.git
cd drbfm-assist

# 2. 開発ヘルパースクリプトを実行
./dev-setup.sh setup

# 3. 環境変数を設定
cp .env.sample .env
# .env ファイルを编集してから進める

# 4. 開発を開始
./dev-setup.sh feature
```

## 🔧 初期セットアップ

### 1. リポジトリのクローン

```bash
# SSH を使用
git clone git@github.com:tmakiya/drbfm-assist.git

# または HTTPS を使用
git clone https://github.com/tmakiya/drbfm-assist.git

cd drbfm-assist
```

### 2. 依存関係のインストール

```bash
# uv を使用（推奨）
uv sync

# または pip を使用
pip install -r requirements.txt
```

### 3. Github CLI 認証

```bash
# GitHub CLI にログイン
gh auth login

# 認証状態を確認
gh auth status
```

### 4. 環境変数の設定

```bash
# サンプルファイルをコピー
cp .env.sample .env

# アカウント認証情報を設定
# - Google Cloud credentials
# - Azure OpenAI credentials
# - Elasticsearch credentials
# - etc.
```

### 5. VS Code ワークスペースの設定

VS Code を開く場合、ワークスペースファイルを使用することをお勧めします：

```bash
code drbfm-assist.code-workspace
```

**ワークスペースの特徴:**
- 複数フォルダの整理
- 推奨拡張機能の自動提案
- Python 開発環境の最適化
- Ruff 統合設定

## 💻 開発ワークフロー

### 開発ヘルパースクリプトの使用

最も簡単な方法は、提供されている `dev-setup.sh` スクリプトを使用することです。

```bash
# インタラクティブメニュー
./dev-setup.sh

# または直接コマンド実行
./dev-setup.sh feature          # 新機能ブランチを作成
./dev-setup.sh quality          # コード品質チェック
./dev-setup.sh test             # テスト実行
./dev-setup.sh push             # 変更をプッシュ
./dev-setup.sh pr               # プルリクエストを作成
```

### 手動での開発ワークフロー

#### Step 1: 新しいブランチを作成

```bash
# feature ブランチを作成
git checkout -b feature/add-fuzzy-search

# 修正 (bugfix) ブランチ
git checkout -b fix/search-timeout

# ドキュメント (docs) ブランチ
git checkout -b docs/update-readme
```

#### Step 2: コード品質チェック

```bash
cd backend

# Ruff でチェック
uv run ruff check .

# Ruff でフォーマット
uv run ruff format .

# Pre-commit フック
pre-commit run --all-files
```

#### Step 3: テスト実行

```bash
cd backend

# すべてのテストを実行
uv run pytest tests/

# 特定のテストファイルを実行
uv run pytest tests/unit_tests/test_search.py -v

# カバレッジを確認
uv run pytest tests/ --cov=drassist
```

#### Step 4: 変更をコミット

```bash
# ファイルをステージ
git add .

# Conventional Commits に従ってコミット
git commit -m "feat(elasticsearch): add fuzzy search support

- Implement fuzzy matching for queries
- Add configuration options
- Include unit tests

Closes #42"
```

#### Step 5: GitHub にプッシュ

```bash
# ブランチをプッシュ
git push -u origin feature/add-fuzzy-search

# 次のプッシュから
git push
```

#### Step 6: プルリクエストを作成

```bash
# GitHub CLI で作成（推奨）
gh pr create --title "Add fuzzy search support" --body "Description"

# または Web UI で作成
# https://github.com/tmakiya/drbfm-assist/compare
```

### コミットメッセージの規約

Conventional Commits を使用しています。

```
<type>(<scope>): <subject>

<body>

<footer>
```

**タイプ:**
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: スタイル変更（スペース、カンマなど）
- `refactor`: コード リファクタリング
- `test`: テスト追加・修正
- `chore`: ビルド・依存関係・ツール・設定の変更
- `perf`: パフォーマンス改善

**例:**

```bash
git commit -m "feat(embeddings): add Azure OpenAI support"
git commit -m "fix(search): resolve timeout issue with large queries"
git commit -m "docs(readme): update installation instructions"
git commit -m "test(elasticsearch): add integration tests"
git commit -m "refactor(chains): simplify workflow logic"
```

## 🔗 GitHub 連携

### リポジトリ情報

- **URL**: https://github.com/tmakiya/drbfm-assist
- **Owner**: tmakiya
- **Visibility**: Public

### ブランチ戦略

```
main (本番環境)
┣━ feature/xxx (機能開発用)
┣━ fix/xxx (バグ修正用)
└━ hotfix/xxx (緊急修正用)

develop (開発用)
┗━ プレリリースの統合ブランチ
```

### リリース手順

1. **機能開発完了**
   ```bash
   git checkout feature/my-feature
   ./dev-setup.sh push
   ./dev-setup.sh pr
   ```

2. **Code Review**
   - GitHub で PR を確認
   - CI チェックに合格することを確認
   - レビュアーに approve を依頼

3. **マージ**
   - PR を Squash & Merge でマージ
   - ブランチを削除

4. **リリース**
   ```bash
   git checkout main
   git pull origin main
   git tag v1.0.0
   git push origin v1.0.0
   ```

## 📝 環境設定

### ローカル環境

#### 必須の環境変数

`.env` ファイルに以下を設定：

```env
# Google Cloud (Vertex AI / Gemini)
GOOGLE_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# Azure OpenAI (Embeddings)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT=your-deployment-name

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200

# Langfuse (オプション)
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
```

#### Python 仮想環境（uv を使用）

```bash
# 依存関係をインストール
uv sync

# 仮想環境をアクティベート
source .venv/bin/activate  # macOS/Linux
# または
.venv\Scripts\activate  # Windows
```

### GitHub Actions シークレット

CI/CD 自動化のため、GitHub リポジトリに以下のシークレットを設定：

**設定場所**: https://github.com/tmakiya/drbfm-assist/settings/secrets/actions

```bash
# GCP 認証
gh secret set GCP_PROJECT_ID --body "your-project-id"
gh secret set GCP_WI_PROVIDER --body "your-provider-id"
gh secret set GCP_WI_SERVICE_ACCOUNT --body "your-service-account"

# Google Cloud Service Account (JSON)
gh secret set GOOGLE_CREDENTIALS --body "$(cat /path/to/credentials.json)"

# Azure OpenAI
gh secret set AZURE_OPENAI_API_KEY --body "your-api-key"
gh secret set AZURE_OPENAI_ENDPOINT --body "https://your-resource.openai.azure.com/"
```

## 🔄 CI/CD パイプライン

### 自動実行されるチェック

PR を作成すると、以下が自動的に実行されます：

1. **コード品質**
   - Ruff lint
   - Ruff format
   - Pre-commit フック

2. **テスト**
   - Unit テスト
   - Integration テスト
   - 実行時間の測定

3. **ビルド**
   - Docker イメージのビルド
   - 成果物の生成

### ワークフローの監視

```bash
# PR に関連するワークフローを確認
gh run list --workflow=ci-cd-drbfm-assist.yml

# ワークフローの詳細を表示
gh run view run-id

# ログを表示
gh run view run-id --log
```

## 🐛 トラブルシューティング

### よくある問題と解決方法

#### 1. Push が拒否される

```bash
# エラー: remote rejected
# 原因: リモートブランチが更新されている

# 解決方法
git fetch origin
git rebase origin/main
git push origin feature/xxx
```

#### 2. マージコンフリクト

```bash
# コンフリクト状態確認
git status

# コンフリクトファイルを編集
# エディタでマーカーを解決:
# <<<<<<< HEAD
# 変更内容 A
# =======
# 変更内容 B
# >>>>>>> branch-name

# 解決済みファイルをマーク
git add .

# コミット
git commit -m "Resolve merge conflicts"
```

#### 3. 大きなコミット履歴の整理

```bash
# インタラクティブ rebase
git rebase -i HEAD~5

# pick/squash/fixup を選択して整理
# コミット を圧縮して履歴を整理
```

#### 4. 誤ったコミットの修正

```bash
# 直前のコミットメッセージを編集
git commit --amend -m "new message"

# 直前のコミットの内容を修正
git add .
git commit --amend --no-edit

# コミットを取り消す（履歴から削除）
git reset --soft HEAD~1  # 変更は保持
git reset --hard HEAD~1  # 変更も削除
```

#### 5. 規約違反エラー

```bash
# Ruff エラーを自動修正
uv run ruff check . --fix

# フォーマットエラーを自動修正
uv run ruff format .

# Pre-commit エラーを確認
pre-commit run --all-files
```

## 📚 参考リソース

### 公式ドキュメント
- [GitHub Documentation](https://docs.github.com)
- [Git Book](https://git-scm.com/book)
- [Conventional Commits](https://www.conventionalcommits.org)
- [Python Best Practices](https://pep8.org)

### プロジェクト内ドキュメント
- [README.md](./README.md) - プロジェクト概要
- [CLAUDE.md](./CLAUDE.md) - Claude AI ガイドライン
- [GITHUB_INTEGRATION.md](./GITHUB_INTEGRATION.md) - GitHub 統合詳細

### ツール
- [GitHub CLI (gh)](https://cli.github.com)
- [uv - Python Package Manager](https://astral.sh/uv)
- [Pre-commit Framework](https://pre-commit.com)
- [Ruff - Python Linter](https://github.com/astral-sh/ruff)

## 💡 ベストプラクティス

1. **定期的な同期**
   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **作業前の確認**
   ```bash
   git status
   git log --oneline -5
   ```

3. **オートセーブ設定**
   - VS Code の `formatOnSave` を有効化
   - Pre-commit フックを有効化

4. **ローカルテスト必須**
   - PR 作成前に必ず `./dev-setup.sh quality` を実行
   - テストに合格することを確認

5. **コミュニケーション**
   - PR に詳細な説明を記載
   - 関連する Issue をリンク
   - レビュアーには親切に

## 🆘 サポート

問題が発生した場合：

1. このドキュメントで解決方法を探す
2. [GitHub Issues](https://github.com/tmakiya/drbfm-assist/issues) で既知の問題を確認
3. 新しい Issue を作成して報告

---

**最後に**: 開発ワークフローが円滑に進むことを願っています！質問やアイデアがあれば、Discussions でお気軽にお知らせください。
