# Docker Desktop インストールガイド（macOS）

## 📥 Step 1: Docker Desktopのインストール

### 方法1: 公式サイトからダウンロード（推奨）

1. **Docker Desktop公式サイトにアクセス**
   - https://www.docker.com/products/docker-desktop/
   - または直接: https://docs.docker.com/desktop/install/mac-install/

2. **ダウンロード**
   - 「Download for Mac」ボタンをクリック
   - あなたのMacのチップに応じて自動的に適切なバージョンが選択されます：
     - **Apple Silicon (M1/M2/M3)**: Apple Chip用
     - **Intel**: Intel Chip用

3. **インストール**
   - ダウンロードした`.dmg`ファイルを開く
   - Dockerアイコンを**Applicationsフォルダにドラッグ&ドロップ**
   - Applicationsフォルダを開いてDockerを起動

4. **初回起動**
   - Docker Desktopが起動すると、メニューバー（画面上部）にDockerアイコン（クジラのアイコン）が表示されます
   - 初回起動時は、セットアップウィザードが表示される場合があります
   - 「Finish」または「Get Started」をクリック

5. **起動確認**
   - メニューバーのDockerアイコンをクリック
   - 「Docker Desktop is running」と表示されていればOK

### 方法2: Homebrewを使用（開発者向け）

```bash
# Homebrewがインストールされている場合
brew install --cask docker

# インストール後、ApplicationsからDockerを起動
open -a Docker
```

## ✅ Step 2: Dockerの動作確認

ターミナルで以下のコマンドを実行して確認：

```bash
# Dockerのバージョン確認
docker --version

# Docker Composeの確認（V2の場合）
docker compose version

# または（V1の場合）
docker-compose --version

# Dockerデーモンが起動しているか確認
docker info
```

**期待される出力例:**
```
Docker version 24.0.0, build abc123
Docker Compose version v2.20.0
Client:
 Context:    default
 Debug Mode: false
 ...
```

## 🚀 Step 3: アプリケーションの起動

### 3-1. 環境変数の設定

```bash
# プロジェクトディレクトリに移動
cd /Users/makiyama/Documents/ai_ui/suzuki

# .envファイルを作成
cp .env.example .env

# .envファイルを編集（必須）
# GOOGLE_APPLICATION_CREDENTIALS=./caddi-cp-it-gemini-internal-2e058b90ed99.json を設定
```

**重要**: `.env`ファイルを開いて、`GOOGLE_APPLICATION_CREDENTIALS`を設定してください。

```bash
# エディタで開く（例：VS Code）
code .env

# またはviで開く
vi .env
```

`.env`ファイルの内容例：
```env
GOOGLE_APPLICATION_CREDENTIALS=./caddi-cp-it-gemini-internal-2e058b90ed99.json
SECRET_KEY=change-me-in-production-please-use-random-string
```

### 3-2. 設定チェック

```bash
# 設定チェックスクリプトを実行
./scripts/docker-check.sh
```

このスクリプトは以下を確認します：
- ✅ Dockerがインストールされているか
- ✅ Dockerが起動しているか
- ✅ .envファイルが存在するか
- ✅ GOOGLE_APPLICATION_CREDENTIALSが設定されているか
- ✅ 認証情報ファイルが存在するか
- ✅ 必要なディレクトリが存在するか
- ✅ ポートが使用可能か

### 3-3. Docker Composeで起動

```bash
# 方法1: Makefileを使用（推奨）
make up

# 方法2: 起動スクリプトを使用
./scripts/docker-start.sh

# 方法3: 直接実行
docker-compose up -d

# または（Docker Compose V2の場合）
docker compose up -d
```

**初回起動時は時間がかかります**（イメージのビルドとダウンロード）

### 3-4. 起動確認

```bash
# サービス状態を確認
make status

# または
docker-compose ps

# ログを確認
make logs

# または
docker-compose logs -f
```

**期待される出力:**
```
NAME                STATUS          PORTS
drawerai-backend    Up (healthy)    0.0.0.0:8000->8000/tcp
drawerai-db         Up (healthy)    0.0.0.0:5432->5432/tcp
drawerai-frontend   Up              0.0.0.0:3000->3000/tcp
drawerai-redis      Up (healthy)    0.0.0.0:6379->6379/tcp
```

### 3-5. 動作テスト

```bash
# 動作テストスクリプトを実行
./scripts/docker-test.sh
```

## 🌐 Step 4: アプリケーションにアクセス

起動が完了したら、ブラウザで以下にアクセス：

1. **フロントエンド**: http://localhost:3000
2. **バックエンドAPI**: http://localhost:8000
3. **APIドキュメント**: http://localhost:8000/docs

## 🔧 トラブルシューティング

### Docker Desktopが起動しない

1. **システム要件を確認**
   - macOS 10.15以上
   - 4GB以上のRAM
   - 仮想化が有効になっているか確認

2. **再起動を試す**
   ```bash
   # Docker Desktopを完全に終了
   # メニューバーのDockerアイコン → Quit Docker Desktop
   
   # 再起動
   open -a Docker
   ```

3. **ログを確認**
   - Docker Desktop → Troubleshoot → View logs

### docker-composeコマンドが見つからない

Docker Desktopの新しいバージョンでは、`docker-compose`（ハイフンあり）の代わりに`docker compose`（ハイフンなし）を使用します。

```bash
# V2を使用（推奨）
docker compose up -d

# または、エイリアスを作成
echo 'alias docker-compose="docker compose"' >> ~/.zshrc
source ~/.zshrc
```

### ポートが既に使用されている

```bash
# ポート8000を使用しているプロセスを確認
lsof -i :8000

# ポート3000を使用しているプロセスを確認
lsof -i :3000

# プロセスを停止（PIDを確認してから）
kill -9 <PID>
```

### イメージのビルドエラー

```bash
# キャッシュなしで再ビルド
docker-compose build --no-cache

# または
docker compose build --no-cache
```

### データベース接続エラー

```bash
# データベースコンテナのログを確認
docker-compose logs db

# データベースコンテナを再起動
docker-compose restart db

# データベースに直接接続して確認
docker-compose exec db psql -U drawerai_user -d drawerai
```

## 📝 よく使うコマンド

### サービスの管理

```bash
# 起動
make up
# または
docker-compose up -d

# 停止
make down
# または
docker-compose down

# 再起動
make restart
# または
docker-compose restart

# 状態確認
make status
# または
docker-compose ps
```

### ログの確認

```bash
# 全サービスのログ
make logs

# 特定のサービスのログ
make logs-backend
make logs-frontend
make logs-db

# または
docker-compose logs -f backend
```

### コンテナ内での操作

```bash
# バックエンドのシェルに入る
make shell-backend
# または
docker-compose exec backend bash

# データベースに接続
make shell-db
# または
docker-compose exec db psql -U drawerai_user -d drawerai
```

### データベース操作

```bash
# データベース初期化
make init
# または
docker-compose exec backend python scripts/init_db.py

# マイグレーション実行
make migrate
# または
docker-compose exec backend alembic upgrade head
```

## 🎯 次のステップ

1. ✅ Docker Desktopをインストール
2. ✅ Docker Desktopを起動
3. ✅ `.env`ファイルを設定
4. ✅ `make up`で起動
5. ✅ http://localhost:3000 にアクセス
6. ✅ ユーザー登録またはログイン（admin/admin123）
7. ✅ ファイルをアップロードして分析を開始

## 📚 参考リンク

- [Docker Desktop公式ドキュメント](https://docs.docker.com/desktop/)
- [Docker Compose公式ドキュメント](https://docs.docker.com/compose/)
- [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)

