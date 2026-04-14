"""Root conftest.py with shared fixtures for all ingestion tests.

Following t-wada's FIRST principles:
- Fast: All external dependencies mocked
- Isolated: Each test gets fresh fixtures
- Repeatable: No external state dependencies
- Self-validating: Clear assertions
- Timely: Tests written alongside code
"""

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest

# Import mock fixtures from mocks/ directory to make them available globally
# These are re-exported here so pytest can discover them
from tests.mocks.gcs_mock import mock_gcs_client, mock_gcs_download_failure  # noqa: F401
from tests.mocks.gemini_mock import mock_gemini_client  # noqa: F401
from tests.mocks.isp_mock import mock_isp_client  # noqa: F401
from tests.mocks.m2m_mock import mock_m2m_token_issuer  # noqa: F401
from tests.mocks.msqp_mock import mock_msqp_client, mock_msqp_token_failure  # noqa: F401

# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure clean environment for each test.

    Removes environment variables that could affect test behavior.
    """
    env_vars_to_clear = [
        "TENANT_ID",
        "ENV",
        "MSQP_HOST",
        "MSQP_ACCESS_TOKEN",
        "MSQP_CLIENT_ID",
        "MSQP_CLIENT_SECRET",
        "ISP_API_URL",
        "M2M_INTERNAL_TOKEN",
        "M2M_INTERNAL_TOKEN_CLIENT_ID",
        "M2M_INTERNAL_TOKEN_CLIENT_SECRET",
        "LOCAL_MODE",
        "GOOGLE_CLOUD_PROJECT",
    ]
    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mock_env_dev(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up development environment variables."""
    env = {
        "TENANT_ID": "test-tenant-123",
        "ENV": "dev",
        "LOCAL_MODE": "false",
        "MSQP_HOST": "dev-msqp-trino.example.com",
        "MSQP_CLIENT_ID": "test-client-id",
        "MSQP_CLIENT_SECRET": "test-client-secret",
        "ISP_API_URL": "https://isp.example.com",
        "M2M_INTERNAL_TOKEN_CLIENT_ID": "m2m-client-id",
        "M2M_INTERNAL_TOKEN_CLIENT_SECRET": "m2m-client-secret",
        "GCS_BUCKET_NAME": "test-bucket",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture
def mock_env_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up environment variables for pipeline tests."""
    env = {
        "TENANT_ID": "test-tenant-123",
        "ENV": "dev",
        "LOCAL_MODE": "true",
        "MSQP_HOST": "dev-msqp-trino.example.com",
        "MSQP_ACCESS_TOKEN": "test-access-token",
        "ISP_API_URL": "http://localhost:3000",
        "GCS_BUCKET_NAME": "test-bucket",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture
def mock_env_local(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up local development environment variables."""
    env = {
        "TENANT_ID": "test-tenant-123",
        "ENV": "dev",
        "LOCAL_MODE": "true",
        "MSQP_HOST": "localhost",
        "MSQP_ACCESS_TOKEN": "local-access-token",
        "ISP_API_URL": "http://localhost:9200",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


# =============================================================================
# JWT Token Fixtures
# =============================================================================


def _create_jwt_token(payload: dict[str, Any]) -> str:
    """Create a mock JWT token with given payload."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    )

    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    signature = "mock_signature"

    return f"{header}.{encoded_payload}.{signature}"


@pytest.fixture
def valid_jwt_token() -> str:
    """Generate a valid mock JWT token with tenant_id claim."""
    return _create_jwt_token(
        {
            "tenant_id": "test-tenant-123",
            "sub": "test-user",
            "exp": 9999999999,
        }
    )


@pytest.fixture
def valid_m2m_jwt_token() -> str:
    """Generate a valid mock M2M JWT token with zoolake tenant_id claim."""
    return _create_jwt_token(
        {
            "https://zoolake.jp/claims/tenantId": "test-tenant-123",
            "sub": "m2m-client",
            "exp": 9999999999,
        }
    )


@pytest.fixture
def invalid_tenant_jwt_token() -> str:
    """Generate a JWT token with wrong tenant_id."""
    return _create_jwt_token(
        {
            "tenant_id": "wrong-tenant-id",
            "sub": "test-user",
            "exp": 9999999999,
        }
    )


# =============================================================================
# Temporary File Fixtures
# =============================================================================


@pytest.fixture
def temp_image_files(tmp_path: Path) -> list[Path]:
    """Create temporary image files for testing."""
    images = []
    for i in range(3):
        img_path = tmp_path / f"test_image_{i}.png"
        # Create a small valid PNG header
        img_path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Minimal PNG-like content
        )
        images.append(img_path)
    return images


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary pipeline config directory."""
    config_dir = tmp_path / "pipeline"
    config_dir.mkdir()

    # Create config.yml
    config_content = """
tenant_id: test-tenant-123

limit: 100
bucket_name: test-bucket
data_dir: /tmp/data

unit_list:
  - テストユニット1
  - テストユニット2

image_analysis:
  model: gemini-2.0-flash
  max_workers: 2
  response_schema:
    type: object
    properties:
      cause_unit:
        type: string
      cause_part:
        type: array
        items:
          type: string
      failure_mode:
        type: string
      failure_effect:
        type: string
      countermeasures:
        type: string

embedding_generation:
  model: text-embedding-004
  source_field: cause_unit
  task_type: RETRIEVAL_DOCUMENT
  dimensionality: 768

isp:
  index_name: test-defects
  id_field: doc_id
  fields:
    doc_id: doc_id
    original_id: original_id
    cause:
      original: cause_original
      unit: cause_unit
      part: cause_part
      part_change: unit_part_change
    failure:
      mode: failure_mode
      effect: failure_effect
    countermeasures: countermeasures
  mappings:
    properties:
      doc_id:
        type: long
      original_id:
        type: keyword
      cause_unit:
        type: text
      embedding:
        type: dense_vector
        dims: 768
  settings:
    number_of_shards: 1
    number_of_replicas: 0
"""
    (config_dir / "config.yml").write_text(config_content, encoding="utf-8")

    # Create query.sql
    (config_dir / "query.sql").write_text("SELECT * FROM drawings LIMIT {limit}", encoding="utf-8")

    # Create prompt.txt
    prompt_content = """You are a defect analysis assistant.
Analyze the following images and extract defect information.

ALLOWED UNIT LIST:
{{unit_list}}
"""
    (config_dir / "prompt.txt").write_text(prompt_content, encoding="utf-8")

    return config_dir


@pytest.fixture
def temp_prompt_file(tmp_path: Path) -> Path:
    """Create a temporary prompt file."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_content = """You are a defect analysis assistant.
Analyze the following images and extract defect information.

ALLOWED UNIT LIST:
{{unit_list}}
"""
    prompt_path.write_text(prompt_content, encoding="utf-8")
    return prompt_path


# =============================================================================
# DataFrame Fixtures
# =============================================================================


@pytest.fixture
def sample_drawing_df(temp_image_files: list[Path]) -> pl.DataFrame:
    """Sample drawing DataFrame with local paths."""
    return pl.DataFrame(
        {
            "drawing_id": ["DRW001", "DRW002", "DRW003"],
            "original_id": ["ORG001", "ORG001", "ORG002"],
            "page_number": [1, 2, 1],
            "file_path": [
                "gs://bucket/path/img1.png",
                "gs://bucket/path/img2.png",
                "gs://bucket/path/img3.png",
            ],
            "blob_path": [
                "path/img1.png",
                "path/img2.png",
                "path/img3.png",
            ],
            "local_path": [str(p) for p in temp_image_files],
        }
    )


@pytest.fixture
def sample_analysis_results() -> list[dict[str, Any]]:
    """Sample Gemini analysis results."""
    return [
        {
            "original_id": "ORG001",
            "drawing_ids": ["DRW001", "DRW002"],
            "page_count": 2,
            "total_size": 1024,
            "status": "success",
            "error_detail": "",
            "cause_original": "原因事象1",
            "cause_unit": "テストユニット1",
            "cause_part": ["部品A", "部品B"],
            "unit_part_change": "変更内容1",
            "failure_mode": "摩耗",
            "failure_effect": "動作不良",
            "countermeasures": "対策内容1",
        },
        {
            "original_id": "ORG002",
            "drawing_ids": ["DRW003"],
            "page_count": 1,
            "total_size": 512,
            "status": "success",
            "error_detail": "",
            "cause_original": "原因事象2",
            "cause_unit": "テストユニット2",
            "cause_part": ["部品C"],
            "unit_part_change": "変更内容2",
            "failure_mode": "破損",
            "failure_effect": "機能停止",
            "countermeasures": "対策内容2",
        },
    ]


@pytest.fixture
def sample_failed_results() -> list[dict[str, Any]]:
    """Sample failed analysis results."""
    return [
        {
            "original_id": "ORG003",
            "drawing_ids": ["DRW004"],
            "page_count": 1,
            "total_size": 60 * 1024 * 1024,  # 60MB - too large
            "status": "skipped_large_file",
            "error_detail": "Total file size exceeds 50MB limit",
        },
        {
            "original_id": "ORG004",
            "drawing_ids": ["DRW005"],
            "page_count": 1,
            "total_size": 1024,
            "status": "image_analysis_error",
            "error_detail": "API rate limit exceeded",
        },
    ]


@pytest.fixture
def sample_response_schema() -> dict[str, Any]:
    """Sample response schema for Gemini."""
    return {
        "type": "object",
        "properties": {
            "cause_original": {"type": "string"},
            "cause_unit": {"type": "string"},
            "cause_part": {"type": "array", "items": {"type": "string"}},
            "unit_part_change": {"type": "string"},
            "failure_mode": {"type": "string"},
            "failure_effect": {"type": "string"},
            "countermeasures": {"type": "string"},
        },
    }


# =============================================================================
# Common Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_google_auth(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock google.auth.default()."""
    mock_creds = MagicMock()
    mock_default = MagicMock(return_value=(mock_creds, "test-project-id"))
    monkeypatch.setattr("google.auth.default", mock_default)
    return mock_default


@pytest.fixture
def mock_vertexai_init(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock vertexai.init()."""
    mock_init = MagicMock()
    monkeypatch.setattr("vertexai.init", mock_init)
    return mock_init
