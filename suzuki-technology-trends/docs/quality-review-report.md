# Production-Ready 品質レビューレポート

**レビュー日**: 2026-01-09

## 前提条件
- **デプロイ先**: GKE（Backend: LangSmith Deployment、Frontend: GKE）
- **認証方式**: 独自JWT認証
- **規模**: 小規模（〜10人）

---

## 1. クリティカル（即時対応必須）

### 1.1 認証システムが完全に無効化されている
**ファイル**: `backend/app/api/endpoints/auth.py`

```python
# Line 87-92: 常にデフォルトユーザーを返す
return User(
    username="default_user",
    email="default@example.com",
    client_id=DEFAULT_CLIENT_ID
)
```

**問題点**:
- 認証なしで全APIにアクセス可能
- パスワード検証が行われていない
- マルチテナント分離が機能しない

**対応**:
- [ ] JWT認証の有効化と実装
- [ ] パスワードハッシュ検証の実装（passlib/bcrypt使用）
- [ ] トークン検証ロジックの実装

---

### 1.2 シークレットのハードコード
**ファイル**: `.env.example:6`, `docker-compose.yml:49`

```
SECRET_KEY=change-me-in-production-please-use-random-string
```

**対応**:
- [ ] GCP Secret Managerからシークレットを取得する仕組みの実装
- [ ] 環境変数での安全な注入

---

### 1.3 Dockerfileが本番用でない
**ファイル**: `frontend/Dockerfile`

```dockerfile
# 開発サーバー起動（本番NG）
CMD ["npm", "run", "dev"]
```

**対応**:
- [ ] マルチステージビルドに変更
- [ ] `npm run build` + `npm start` に変更
- [ ] 非rootユーザーでの実行

---

## 2. 重要（リリース前に対応）

### 2.1 Backend

| 問題 | ファイル | 対応 |
|------|----------|------|
| CORS設定が緩すぎる | `main.py:47-48` | allow_originsを本番URLに限定 |
| レート制限が緩すぎる | `main.py:40` | 10000req/minは多すぎる |
| エラーハンドリング不足 | 各endpoint | グローバル例外ハンドラ追加 |
| ログ構造化されていない | 全体 | JSON形式ログに変更 |
| テスト不足 | `tests/` | カバレッジ向上（現在2ファイルのみ） |
| 入力バリデーション不足 | 各endpoint | Pydantic validatorの強化 |

### 2.2 Frontend

| 問題 | ファイル | 対応 |
|------|----------|------|
| `any`型の使用 | `lib/api.ts:70` | 型定義の厳密化 |
| Error Boundaryなし | `_app.tsx` | グローバルエラーハンドラ追加 |
| CSRF対策なし | `lib/api.ts` | CSRFトークン実装 |
| ローディング状態が簡素 | 各ページ | Skeleton UI等の導入 |
| アクセシビリティ不足 | 各コンポーネント | セマンティックHTML、ARIA属性 |
| 環境変数フォールバック | `api.ts:9` | localhost fallbackは危険 |

### 2.3 インフラ

| 問題 | ファイル | 対応 |
|------|----------|------|
| CI/CDなし | - | GitHub Actions追加 |
| 本番Dockerfile未整備 | `frontend/Dockerfile` | マルチステージビルド |
| ヘルスチェック簡素 | `main.py:71-74` | DB/Redis接続確認追加 |
| package-lock.json未確認 | `frontend/` | 依存関係のロック |

---

## 3. 推奨（品質向上）

### 3.1 セキュリティ強化
- [ ] Helmet相当のセキュリティヘッダー（一部実装済み）
- [ ] Content Security Policy (CSP) の設定
- [ ] 依存関係の脆弱性スキャン（Dependabot/Snyk）

### 3.2 可観測性
- [ ] 構造化ログ（JSON形式）
- [ ] メトリクス収集（Prometheus形式）
- [ ] 分散トレーシング（OpenTelemetry）

### 3.3 コード品質
- [ ] Linter/Formatter統一（Black, Ruff, ESLint, Prettier）
- [ ] pre-commitフック設定
- [ ] 型チェック強化（mypy, tsc strict mode）

---

## 4. 対応優先順位

### Phase 1: 必須（本番リリース前）
1. JWT認証の有効化・実装
2. シークレット管理（Secret Manager連携）
3. Frontend Dockerfileの本番化
4. CORS設定の厳格化
5. 基本的なエラーハンドリング

### Phase 2: 重要（早期対応）
1. テストカバレッジ向上
2. CI/CDパイプライン構築
3. 構造化ログ
4. フロントエンド型定義強化

### Phase 3: 改善（継続的）
1. アクセシビリティ対応
2. パフォーマンス最適化
3. 可観測性強化

---

## 5. 修正対象ファイル一覧

### Backend
- `backend/app/api/endpoints/auth.py` - 認証実装
- `backend/app/main.py` - CORS、レート制限、エラーハンドリング
- `backend/app/middleware/security.py` - セキュリティ強化
- `backend/Dockerfile` - 非rootユーザー
- `backend/tests/` - テスト追加

### Frontend
- `frontend/src/lib/api.ts` - 型定義、エラーハンドリング
- `frontend/src/pages/_app.tsx` - Error Boundary
- `frontend/Dockerfile` - 本番ビルド
- `frontend/package.json` - scripts更新

### インフラ
- `.github/workflows/` - CI/CD追加
- `docker-compose.production.yml` - 本番設定確認
- 新規: Secret Manager連携スクリプト

---

## 6. 良い点（既に実装済み）

- セキュリティヘッダーミドルウェア（`SecurityHeadersMiddleware`）
- レート制限ミドルウェア（`RateLimitMiddleware`）
- ヘルスチェックエンドポイント（`/health`）
- Pydanticによる基本的な入力バリデーション
- SQLAlchemyによるSQLインジェクション対策
- Docker Compose環境の整備
