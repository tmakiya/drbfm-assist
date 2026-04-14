"""Unit tests for MSQPClient."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from common.msqp.client import MSQPClient, create_msqp_client_from_env

# Import mock fixtures
from tests.mocks.msqp_mock import mock_msqp_client, mock_msqp_token_failure  # noqa: F401


class TestMSQPClientInit:
    """Tests for MSQPClient initialization."""

    def test_init_with_access_token(self, mock_env_dev: dict[str, str]) -> None:
        """Test initialization with direct access token."""
        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        assert client.host == "test-host"
        assert client.tenant_id == "test-tenant-123"
        assert client.access_token == "test-token"
        assert client.catalog == "drawing"
        assert client.schema == "msqp__drawing"

    def test_init_with_custom_catalog_schema(self, mock_env_dev: dict[str, str]) -> None:
        """Test initialization with custom catalog and schema."""
        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
            catalog="custom-catalog",
            schema="custom-schema",
        )

        assert client.catalog == "custom-catalog"
        assert client.schema == "custom-schema"

    def test_init_without_credentials_raises(self, mock_env_dev: dict[str, str]) -> None:
        """Test that missing credentials raises ValueError."""
        with pytest.raises(ValueError, match="Either access_token or"):
            MSQPClient(
                host="test-host",
                tenant_id="test-tenant-123",
            )

    def test_init_with_only_client_id_raises(self, mock_env_dev: dict[str, str]) -> None:
        """Test that providing only client_id raises ValueError."""
        with pytest.raises(ValueError, match="Either access_token or"):
            MSQPClient(
                host="test-host",
                tenant_id="test-tenant-123",
                client_id="client-id",
            )

    def test_init_with_client_credentials(
        self,
        mock_msqp_client,  # noqa: F811
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test initialization with client credentials obtains token."""
        mocks = mock_msqp_client()

        client = MSQPClient(
            host="dev-msqp-trino.zoolake.jp",
            tenant_id="test-tenant-123",
            client_id="client-id",
            client_secret="client-secret",
        )

        assert client.access_token == mocks["token"]
        mocks["post"].assert_called_once()


class TestMSQPClientTokenObtain:
    """Tests for token acquisition."""

    def test_token_acquisition_success(
        self,
        mock_msqp_client,  # noqa: F811
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test successful token acquisition."""
        mocks = mock_msqp_client()

        client = MSQPClient(
            host="dev-msqp-trino.zoolake.jp",
            tenant_id="test-tenant-123",
            client_id="client-id",
            client_secret="client-secret",
        )

        # Verify the token was obtained
        assert client.access_token is not None
        # Verify the request was made
        mocks["post"].assert_called_once()

    def test_token_acquisition_failure(
        self,
        mock_msqp_token_failure,  # noqa: F811
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test token acquisition failure raises exception."""
        with pytest.raises(Exception, match="Token acquisition failed"):
            MSQPClient(
                host="dev-msqp-trino.zoolake.jp",
                tenant_id="test-tenant-123",
                client_id="client-id",
                client_secret="client-secret",
            )

    def test_token_tenant_id_mismatch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        invalid_tenant_jwt_token: str,
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test that tenant_id mismatch raises ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": invalid_tenant_jwt_token}
        monkeypatch.setattr("requests.post", MagicMock(return_value=mock_response))

        with pytest.raises(ValueError, match="Tenant ID mismatch"):
            MSQPClient(
                host="dev-msqp-trino.zoolake.jp",
                tenant_id="test-tenant-123",
                client_id="client-id",
                client_secret="client-secret",
            )


class TestMSQPClientQuery:
    """Tests for MSQPClient.query method."""

    def test_query_returns_dataframe(
        self,
        mock_msqp_client,  # noqa: F811
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test that query returns a polars DataFrame."""
        expected_df = pl.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["a", "b", "c"],
            }
        )
        mock_msqp_client(query_result=expected_df)

        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        result = client.query("SELECT * FROM test")

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        assert result.columns == ["id", "name"]

    def test_query_empty_result(
        self,
        mock_msqp_client,  # noqa: F811
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test query with empty result returns empty DataFrame."""
        mock_msqp_client(query_result=pl.DataFrame())

        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        result = client.query("SELECT * FROM empty_table")

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0


class TestGetTenantIdFromToken:
    """Tests for static tenant_id extraction from JWT."""

    def test_extract_tenant_id_success(self, valid_jwt_token: str) -> None:
        """Test successful tenant_id extraction."""
        tenant_id = MSQPClient.get_tenant_id_from_token(valid_jwt_token)

        assert tenant_id == "test-tenant-123"

    def test_extract_invalid_token_format_raises(self) -> None:
        """Test that invalid token format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JWT format"):
            MSQPClient.get_tenant_id_from_token("not-a-jwt")

    def test_extract_token_without_tenant_id_raises(self) -> None:
        """Test that token without tenant_id raises ValueError."""
        import base64
        import json

        # Create token without tenant_id claim
        header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({"sub": "test"}).encode()).decode().rstrip("=")
        token = f"{header}.{payload}.signature"

        with pytest.raises(ValueError, match="tenant_id not found"):
            MSQPClient.get_tenant_id_from_token(token)


class TestMSQPClientGetAuthUrl:
    """Tests for auth URL determination."""

    def test_auth_url_from_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test auth URL from environment variable."""
        monkeypatch.setenv("MSQP_AUTH_URL", "https://custom-auth.example.com/token")

        client = MSQPClient(
            host="any-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        assert client._get_auth_url() == "https://custom-auth.example.com/token"

    def test_auth_url_from_dev_host(self, mock_env_dev: dict[str, str]) -> None:
        """Test auth URL determined from dev host."""
        client = MSQPClient(
            host="dev-msqp-trino.zoolake.jp",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        assert client._get_auth_url() == "https://dev-msqp-auth.zoolake.jp/oauth2/token"

    def test_auth_url_from_stg_host(self, mock_env_dev: dict[str, str]) -> None:
        """Test auth URL determined from stg host."""
        client = MSQPClient(
            host="stg-msqp-trino.zoolake.jp",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        assert client._get_auth_url() == "https://stg-msqp-auth.zoolake.jp/oauth2/token"

    def test_auth_url_from_prod_host(self, mock_env_dev: dict[str, str]) -> None:
        """Test auth URL determined from prod host."""
        client = MSQPClient(
            host="prod-msqp-trino.zoolake.jp",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        assert client._get_auth_url() == "https://prod-msqp-auth.zoolake.jp/oauth2/token"

    def test_auth_url_unknown_host_raises(self, mock_env_dev: dict[str, str]) -> None:
        """Test that unknown host without env var raises ValueError."""
        client = MSQPClient(
            host="unknown-host.example.com",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        with pytest.raises(ValueError, match="Cannot determine MSQP_AUTH_URL"):
            client._get_auth_url()


class TestMSQPClientProxies:
    """Tests for proxy configuration."""

    def test_no_proxies_in_non_local_mode(self, mock_env_dev: dict[str, str]) -> None:
        """Test that no proxies are configured in non-local mode."""
        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
            local_mode=False,
        )

        assert client._get_proxies() is None

    def test_proxies_in_local_mode(self, mock_env_local: dict[str, str]) -> None:
        """Test that proxies are configured in local mode."""
        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
            local_mode=True,
        )

        proxies = client._get_proxies()
        assert proxies is not None
        assert "https" in proxies
        assert "http" in proxies


class TestCreateMSQPClientFromEnv:
    """Tests for create_msqp_client_from_env factory function."""

    def test_create_from_env_with_access_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test creating client from env with access token."""
        monkeypatch.setenv("TENANT_ID", "env-tenant-123")
        monkeypatch.setenv("MSQP_HOST", "env-host.example.com")
        monkeypatch.setenv("MSQP_ACCESS_TOKEN", "env-access-token")

        client = create_msqp_client_from_env()

        assert client.host == "env-host.example.com"
        assert client.tenant_id == "env-tenant-123"
        assert client.access_token == "env-access-token"

    def test_create_from_env_missing_tenant_id_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that missing TENANT_ID raises ValueError."""
        # Ensure TENANT_ID is not set (clean_environment fixture already does this)

        with pytest.raises(ValueError, match="TENANT_ID environment variable is required"):
            create_msqp_client_from_env()

    def test_create_from_env_local_mode_detection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test local mode detection from environment."""
        monkeypatch.setenv("TENANT_ID", "env-tenant-123")
        monkeypatch.setenv("MSQP_ACCESS_TOKEN", "env-access-token")
        monkeypatch.setenv("LOCAL_MODE", "true")

        client = create_msqp_client_from_env()

        assert client.local_mode is True


class TestMSQPClientUse:
    """Tests for MSQPClient.use method."""

    def test_use_catalog_and_schema(
        self,
        mock_msqp_client,  # noqa: F811
        mock_env_dev: dict[str, str],
    ) -> None:
        """Test changing both catalog and schema."""
        mock_msqp_client()

        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        client.use(catalog="new-catalog", schema="new-schema")

        assert client.catalog == "new-catalog"
        assert client.schema == "new-schema"

    def test_use_neither_raises(self, mock_env_dev: dict[str, str]) -> None:
        """Test that calling use() without arguments raises ValueError."""
        client = MSQPClient(
            host="test-host",
            tenant_id="test-tenant-123",
            access_token="test-token",
        )

        with pytest.raises(ValueError, match="At least one of"):
            client.use()
