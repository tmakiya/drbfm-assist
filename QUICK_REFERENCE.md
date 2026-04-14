# GitHub 連携 - クイックリファレンス

## 🚀 最初の一度だけ

```bash
# 1. プロジェクトをクローン
git clone https://github.com/tmakiya/drbfm-assist.git
cd drbfm-assist

# 2. セットアップ実行
./dev-setup.sh setup

# 3. 環境変数を設定
cp .env.sample .env
# エディタで機密情報を追加
```

## 💻 日常の開発（ヘルパースクリプト使用）

### インタラクティブメニュー
```bash
./dev-setup.sh
```

### または直接コマンド実行
```bash
# 新機能開発をスタート
./dev-setup.sh feature

# コード品質チェック
./dev-setup.sh quality

# テスト実行
./dev-setup.sh test

# GitHub にプッシュ
./dev-setup.sh push

# PR を作成
./dev-setup.sh pr

# ブランチを更新
./dev-setup.sh update

# Git ステータス確認
./dev-setup.sh status
```

## 🔧 手動での開発

### 新機能ブランチを作成
```bash
git checkout -b feature/feature-name
```

### コード品質チェック
```bash
cd backend
uv run ruff check .          # Check
uv run ruff format .         # Format
pre-commit run --all-files   # Pre-commit hooks
```

### テスト実行
```bash
cd backend
uv run pytest tests/ -v
```

### コミット
```bash
git add .
git commit -m "feat(module): description"
```

### プッシュと PR 作成
```bash
git push -u origin feature/feature-name
gh pr create --title "Title" --body "Description"
```

## 📋 コミットメッセージの型

| Type | 用途 | 例 |
|------|------|-----|
| `feat` | 新機能 | `feat(search): add fuzzy matching` |
| `fix` | バグ修正 | `fix(api): resolve timeout error` |
| `docs` | ドキュメント | `docs(readme): update setup` |
| `style` | スタイル | `style: remove trailing whitespace` |
| `refactor` | リファクタリング | `refactor(core): simplify logic` |
| `test` | テスト | `test(search): add unit tests` |
| `chore` | その他 | `chore(deps): update dependencies` |

## 📌 ブランチ名の規則

```
feature/description       # 新機能
fix/description           # バグ修正
docs/description          # ドキュメント
chore/description         # その他
```

## 🔗 よく使う GitHub CLI コマンド

```bash
# PR を作成
gh pr create --title "Title" --body "Description"

# PR のステータスを確認
gh pr status

# PR を見る
gh pr view

# ローカリタイを見る
gh pr view -w

# Issue を確認
gh issue list

# リポジトリをブラウザで開く
gh repo view -w
```

## 🐛 よくあるトラブル

| 問題 | 解決方法 |
|------|---------|
| Push が拒否される | `git fetch origin` → `git rebase origin/main` → `git push` |
| マージコンフリクト | ファイルを編集 → `git add .` → `git commit` |
| Ruff エラー | `uv run ruff format .` で自動修正 |
| テスト失敗 | `uv run pytest tests/ -v` で詳細確認 |
| ブランチに取り残される | `git checkout main` → `git pull` |

## 📚 ドキュメント

- **設定ガイド**: [GITHUB_SETUP_GUIDE.md](./GITHUB_SETUP_GUIDE.md)
- **開発ガイド**: [GITHUB_DEV_GUIDE.md](./GITHUB_DEV_GUIDE.md)
- **統合詳細**: [GITHUB_INTEGRATION.md](./GITHUB_INTEGRATION.md)
- **プロジェクト**: [README.md](./README.md)

## 🔗 リンク

- **リポジトリ**: https://github.com/tmakiya/drbfm-assist
- **Issues**: https://github.com/tmakiya/drbfm-assist/issues
- **Discussions**: https://github.com/tmakiya/drbfm-assist/discussions
- **Actions**: https://github.com/tmakiya/drbfm-assist/actions

---

### 💡 Tips

- VS Code で `drbfm-assist.code-workspace` を開く
- 開発前に `./dev-setup.sh quality` を実行
- PR 作成前に必ずテストを実行
- コミットメッセージは記述的に
