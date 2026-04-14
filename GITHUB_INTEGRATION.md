# GitHub 連携設定ガイド

## 概要

このドキュメントでは、drbfm-assist プロジェクトを GitHub リポジトリと連携させるための設定手順を説明します。

## 現在の状態

- ✅ Git リポジトリが初期化済み
- ✅ `.gitignore` が設定済み
- ✅ GitHub Actions ワークフローが複数存在

## 必要な設定

### 1. GitHub リポジトリの作成

```bash
# GitHub で新しいリポジトリを作成
# https://github.com/new

# ローカルでリモートを追加
cd /Users/makiyama/Documents/drbfm-assist-main
git remote add origin https://github.com/YOUR_USERNAME/drbfm-assist.git

# 確認
git remote -v
```

### 2. 初期コミット

```bash
# 全てのファイルをステージ
git add .

# 初期コミット
git commit -m "Initial commit: DRBFM Assist Prototype"

# main ブランチにリネーム
git branch -M main

# プッシュ
git push -u origin main
```

### 3. 環境変数の設定

`.env` ファイルは `.gitignore` で除外されているため、GitHub にはアップロードされません。

```bash
# 環境変数のサンプルをコピー
cp .env.sample .env

# .env ファイルを編集（機密情報を設定）
# - Google Cloud credentials
# - Azure OpenAI credentials
# - Elasticsearch credentials
```

### 4. GitHub Secrets の設定

GitHub リポジトリの `Settings > Secrets and variables > Actions` で以下のシークレットを設定:

- `GOOGLE_CREDENTIALS`: Google Cloud 認証情報（JSON 形式）
- `AZURE_OPENAI_API_KEY`: Azure OpenAI API キー
- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI エンドポイント
- `ELASTICSEARCH_URL`: Elasticsearch URL
- `ELASTICSEARCH_API_KEY`: Elasticsearch API キー

### 5. 既存の GitHub Actions ワークフロー

以下のワークフローが既に設定されています:

#### CI/CD ワークフロー

1. **build-and-push-denso-aipfmea-backend.yml**
   - Denso PFMEA バックエンドのビルドとプッシュ

2. **build-and-push-denso-aipfmea-frontend.yml**
   - Denso PFMEA フロントエンドのビルドとプッシュ

3. **build-suzuki-backend.yml**
   - Suzuki Technology Trends バックエンドのビルド

4. **deploy-ingestion.yml**
   - データ取り込みジョブのデプロイ

5. **deploy-ui.yml**
   - UI のデプロイ

6. **deploy-workflow.yml**
   - DRBFM ワークフローのデプロイ

7. **ci-ingestion.yml**
   - 取り込みジョブの CI

8. **determine-environment.yml**
   - 環境の自動判定

### 6. 開発ワークフロー

```bash
# 新規機能の開発
git checkout -b feature/your-feature-name

# 変更をステージ
git add .

# コミット
git commit -m "feat: add your feature description"

# main にマージ
git checkout main
git merge feature/your-feature-name

# プッシュ
git push origin main
```

### 7. Pre-commit フック

```bash
# pre-commit のインストール
pip install pre-commit

# 設定
pre-commit install

# 手動実行
pre-commit run --all-files
```

### 8. Docker Registry の設定

GitHub Container Registry (GHCR) を使用:

```bash
# Docker ログイン
echo ${{ secrets.GITHUB_TOKEN }} | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# イメージのタグ付け
docker tag drbfm-assist-backend:latest ghcr.io/YOUR_USERNAME/drbfm-assist-backend:latest
docker tag drbfm-assist-frontend:latest ghcr.io/YOUR_USERNAME/drbfm-assist-frontend:latest

# プッシュ
docker push ghcr.io/YOUR_USERNAME/drbfm-assist-backend:latest
docker push ghcr.io/YOUR_USERNAME/drbfm-assist-frontend:latest
```

## 推奨事項

1. **Branch Protection Rules**: main ブランチに保護ルールを設定
2. **Code Owners**: `.github/CODEOWNERS` ファイルでコードオーナーを定義
3. **Dependabot**: 自動依存関係更新を有効化（既に設定済み）
4. **Issue Templates**: イシューテンプレートを作成
5. **Pull Request Templates**: PR テンプレートを作成

## トラブルシューティング

### コミットがプッシュできない場合

```bash
# 遠隔リポジトリを確認
git remote -v

# リモートを再設定
git remote set-url origin https://github.com/YOUR_USERNAME/drbfm-assist.git

# 強制的にプッシュ（必要に応じて）
git push -f origin main
```

### 機密情報がコミットされた場合

```bash
# git-filter-repository を使用
pip install git-filter-repo

# 機密情報を削除
git filter-repo --invert-paths .env

# 強制的にプッシュ
git push origin main --force
```

## 参考リソース

- [GitHub Actions ドキュメント](https://docs.github.com/ja/actions)
- [GitHub Secrets ドキュメント](https://docs.github.com/ja/actions/security-guides/using-secrets-in-github-actions)
- [Docker と GitHub Actions の統合](https://docs.github.com/ja/actions/publishing-packages/publishing-docker-images)
