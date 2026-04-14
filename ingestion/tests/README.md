# テスト戦略ドキュメント

このドキュメントでは、`ingestion/` モジュールのテスト戦略について説明します。

## 基本方針

本プロジェクトのテストは、**t-wada氏のFIRST原則**に基づいて設計されています。

| 原則 | 説明 | 実装方法 |
|------|------|----------|
| **F**ast | テストは高速に実行される | すべての外部依存をモック化 |
| **I**solated | 各テストは独立している | フィクスチャで毎回新しい状態を生成 |
| **R**epeatable | 何度実行しても同じ結果 | 外部状態への依存を排除 |
| **S**elf-validating | 成功/失敗が明確 | 明確なアサーションを使用 |
| **T**imely | コードと同時にテストを書く | 機能実装と並行してテスト作成 |

## ディレクトリ構成

```
tests/
├── README.md                 # 本ドキュメント
├── __init__.py
├── conftest.py               # 共有フィクスチャ
├── fixtures/
│   ├── __init__.py
│   └── sample_data.py        # サンプルデータ生成
├── mocks/
│   ├── __init__.py
│   ├── gemini_mock.py        # Gemini API モック
│   ├── gcs_mock.py           # GCS クライアントモック
│   ├── isp_mock.py           # ISP クライアントモック
│   ├── m2m_mock.py           # M2M トークンモック
│   └── msqp_mock.py          # MSQP (Trino) モック
└── unit/
    ├── __init__.py
    ├── pipelines/
    │   ├── __init__.py
    │   ├── test_ingest.py    # インジェストモジュールテスト
    │   ├── test_pipeline.py  # パイプラインテスト
    │   └── test_processing.py # 処理モジュールテスト
    ├── test_gcs_client.py    # GCS クライアントテスト
    ├── test_gemini_client.py # Gemini クライアントテスト
    ├── test_isp_client.py    # ISP クライアントテスト
    └── test_msqp_client.py   # MSQP クライアントテスト
```

## テストの実行方法

```bash
# すべてのユニットテストを実行
uv run pytest tests/unit/ -v

# カバレッジレポート付きで実行
uv run pytest tests/unit/ --cov=common --cov-report=term-missing

# 特定のテストファイルを実行
uv run pytest tests/unit/test_msqp_client.py -v

# 特定のテストクラスを実行
uv run pytest tests/unit/test_msqp_client.py::TestMSQPClientQuery -v

# 特定のテストを実行
uv run pytest tests/unit/test_msqp_client.py::TestMSQPClientQuery::test_query_returns_dataframe -v

# 失敗時に即座に停止
uv run pytest tests/unit/ -x

# 前回失敗したテストのみ再実行
uv run pytest tests/unit/ --lf
```

## モック戦略

### 外部依存のモック化

すべての外部サービス呼び出しはモック化され、ネットワーク通信なしでテストが実行されます。

| サービス | モックファイル | モック対象 |
|----------|----------------|------------|
| MSQP (Trino) | `mocks/msqp_mock.py` | データベース接続、クエリ実行 |
| GCS | `mocks/gcs_mock.py` | ファイルダウンロード、バケット操作 |
| Gemini AI | `mocks/gemini_mock.py` | 画像解析、埋め込み生成 |
| ISP | `mocks/isp_mock.py` | インデックス操作、ドキュメント登録 |
| M2M Token | `mocks/m2m_mock.py` | トークン取得 |

**重要:** モックフィクスチャは `tests/conftest.py` でインポートされ、pytest により自動的に検出されます。新しいモックフィクスチャを追加した場合は、`conftest.py` のインポート文も更新してください。

```python
# tests/conftest.py
from tests.mocks.gcs_mock import mock_gcs_client, mock_gcs_download_failure  # noqa: F401
from tests.mocks.gemini_mock import mock_gemini_client  # noqa: F401
from tests.mocks.isp_mock import mock_isp_client  # noqa: F401
from tests.mocks.m2m_mock import mock_m2m_token_issuer  # noqa: F401
from tests.mocks.msqp_mock import mock_msqp_client, mock_msqp_token_failure  # noqa: F401
```

### ファクトリーフィクスチャパターン

モックは**ファクトリーフィクスチャパターン**を採用し、テストごとに異なる振る舞いを設定できます。

```python
# 使用例: MSQP モック
def test_query_returns_dataframe(mock_msqp_client):
    # 期待する結果を設定
    expected_df = pl.DataFrame({
        "drawing_id": ["D1", "D2"],
        "original_id": ["O1", "O1"],
    })

    # モックを設定
    mock_msqp_client(query_result=expected_df)

    # テスト対象を実行
    client = MSQPClient(...)
    result = client.query("SELECT * FROM drawings")

    # 検証
    assert len(result) == 2
```

```python
# 使用例: Gemini モック（エラーケース）
def test_api_error_handling(mock_gemini_client):
    # エラーを発生させる設定
    mock_gemini_client(generate_error=Exception("API rate limit exceeded"))

    # テスト対象を実行し、エラーハンドリングを検証
    result = analyze_images(...)
    assert result["status"] == "error"
```

## フィクスチャ一覧

### 環境フィクスチャ (`conftest.py`)

| フィクスチャ名 | 説明 |
|----------------|------|
| `clean_environment` | 各テスト前に環境変数をクリア（autouse） |
| `mock_env_dev` | 開発環境の環境変数を設定 |
| `mock_env_pipeline` | パイプラインテスト用環境変数を設定 |
| `mock_env_local` | ローカル開発環境の環境変数を設定 |

### JWTトークンフィクスチャ (`conftest.py`)

| フィクスチャ名 | 説明 |
|----------------|------|
| `valid_jwt_token` | 有効なテナントIDを持つJWTトークン |
| `valid_m2m_jwt_token` | M2M認証用のJWTトークン |
| `invalid_tenant_jwt_token` | 無効なテナントIDを持つJWTトークン |

### 一時ファイルフィクスチャ (`conftest.py`)

| フィクスチャ名 | 説明 |
|----------------|------|
| `temp_image_files` | テスト用の一時画像ファイル（3枚） |
| `temp_config_dir` | パイプライン設定ディレクトリ |
| `temp_prompt_file` | プロンプトファイル |

### データフィクスチャ (`conftest.py`)

| フィクスチャ名 | 説明 |
|----------------|------|
| `sample_drawing_df` | サンプル図面DataFrame |
| `sample_analysis_results` | 成功した解析結果サンプル |
| `sample_failed_results` | 失敗した解析結果サンプル |
| `sample_response_schema` | Gemini用レスポンススキーマ |

## テストカテゴリ

### 1. ユニットテスト (`tests/unit/`)

個々のクラス・関数を独立してテストします。

**テスト対象:**
- クライアントの初期化
- メソッドの正常系・異常系
- エラーハンドリング
- 境界値

### 2. パイプラインテスト (`tests/unit/pipelines/`)

パイプラインの各ステージをテストします。

**テスト対象:**
- データ取得 (`fetching`)
- データ処理 (`processing`)
- データ登録 (`ingest`)
- パイプライン全体 (`pipeline`)

## テスト命名規則

```python
class Testクラス名:
    """テストクラスの説明"""

    def test_機能_条件_期待結果(self):
        """テストの説明"""
        pass
```

**例:**
```python
class TestMSQPClientQuery:
    """Tests for MSQPClient.query method."""

    def test_query_returns_dataframe(self):
        """Test that query returns a polars DataFrame."""
        pass

    def test_query_empty_result(self):
        """Test query with no results returns empty DataFrame."""
        pass
```

## 環境分離

テストは本番環境や外部サービスに一切依存しません。

```python
@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure clean environment for each test."""
    env_vars_to_clear = [
        "TENANT_ID",
        "ENV",
        "MSQP_HOST",
        "MSQP_ACCESS_TOKEN",
        # ... 他の環境変数
    ]
    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)
```

## カバレッジ目標

| モジュール | 現在のカバレッジ | 目標 |
|------------|------------------|------|
| `common/gcs/` | 98% | 95%+ |
| `common/gemini/` | 96% | 95%+ |
| `common/isp/` | 89% | 90%+ |
| `common/msqp/` | 87% | 90%+ |
| `common/pipelines/` | 85-97% | 90%+ |
| **全体** | **85%** | **90%+** |

## 新しいテストの追加方法

### 1. クライアントのテストを追加する場合

```python
# tests/unit/test_new_client.py

from common.new_module.client import NewClient

class TestNewClientInit:
    """Tests for NewClient initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        client = NewClient()
        assert client.timeout == 30

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        client = NewClient(timeout=60)
        assert client.timeout == 60
```

### 2. モックを追加する場合

```python
# tests/mocks/new_mock.py

import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_new_service(monkeypatch: pytest.MonkeyPatch):
    """Fixture to mock new service dependencies."""

    def _create_mock(
        response_data: dict | None = None,
        should_fail: bool = False,
    ) -> dict:
        mock_client = MagicMock()

        if should_fail:
            mock_client.call.side_effect = Exception("Service error")
        else:
            mock_client.call.return_value = response_data or {}

        monkeypatch.setattr(
            "common.new_module.client.ExternalService",
            MagicMock(return_value=mock_client)
        )

        return {"client": mock_client}

    return _create_mock
```

### 3. フィクスチャを追加する場合

`tests/conftest.py` に追加:

```python
@pytest.fixture
def new_sample_data() -> dict:
    """Sample data for new feature tests."""
    return {
        "id": "test-123",
        "name": "テストデータ",
        "values": [1, 2, 3],
    }
```

## トラブルシューティング

### テストが失敗する場合

1. **環境変数の問題**
   ```bash
   # 環境変数が正しくクリアされているか確認
   uv run pytest tests/unit/test_xxx.py -v --capture=no
   ```

2. **モックが正しく適用されていない**
   - モックのパスが正しいか確認（インポート元でモック）
   ```python
   # 正しい: インポート先でモック
   monkeypatch.setattr("common.msqp.client.connect", mock_connect)

   # 誤り: 元のモジュールでモック
   monkeypatch.setattr("trino.dbapi.connect", mock_connect)
   ```

3. **フィクスチャの依存関係**
   - `mock_env_pipeline` などの環境フィクスチャを忘れずに追加

### カバレッジが低い場合

1. 未テストのブランチを確認:
   ```bash
   uv run pytest tests/unit/ --cov=common --cov-report=html
   # htmlcov/index.html を開いて確認
   ```

2. 不足しているテストケースを追加

## 参考資料

- [pytest 公式ドキュメント](https://docs.pytest.org/)
- [pytest-mock](https://pytest-mock.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [t-wada TDD/テスト講演](https://speakerdeck.com/twada)
