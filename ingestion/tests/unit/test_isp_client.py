"""Unit tests for ISPClient."""

from unittest.mock import MagicMock

import pytest
from common.isp.client import ISPClient, create_isp_client_from_env

# Import mock fixtures
from tests.mocks.isp_mock import (
    MockISPResponse,
    MockISPSession,
)  # noqa: F401


class TestISPClientInit:
    """Tests for ISPClient initialization."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        client = ISPClient()

        assert client.base_url == "http://localhost:3000"
        assert client.tenant_id is None
        assert client.timeout == 30
        assert client.internal_token is None

    def test_init_custom_values(self) -> None:
        """Test initialization with custom values."""
        client = ISPClient(
            base_url="https://isp.example.com/",
            tenant_id="test-tenant",
            timeout=60,
            internal_token="test-token",
        )

        assert client.base_url == "https://isp.example.com"  # Trailing slash removed
        assert client.tenant_id == "test-tenant"
        assert client.timeout == 60
        assert client.internal_token == "test-token"

    def test_session_trust_env_disabled(self) -> None:
        """Test that session.trust_env is disabled."""
        client = ISPClient()

        assert client.session.trust_env is False


class TestISPClientHeaders:
    """Tests for ISPClient._headers method."""

    def test_headers_with_internal_token(self) -> None:
        """Test headers when internal token is set."""
        client = ISPClient(
            internal_token="test-token",
            tenant_id="test-tenant",
        )

        headers = client._headers()

        assert headers["Authorization"] == "Bearer test-token"
        assert "x-caddi-tenant-id" not in headers  # Token contains tenant info

    def test_headers_with_tenant_only(self) -> None:
        """Test headers when only tenant_id is set."""
        client = ISPClient(tenant_id="test-tenant")

        headers = client._headers()

        assert headers["x-caddi-tenant-id"] == "test-tenant"
        assert "Authorization" not in headers

    def test_headers_content_type(self) -> None:
        """Test that Content-Type is always set."""
        client = ISPClient()

        headers = client._headers()

        assert headers["Content-Type"] == "application/json"


class TestISPClientHealthCheck:
    """Tests for ISPClient.health_check method."""

    def test_health_check_success(
        self,
        mock_isp_client,  # noqa: F811
    ) -> None:
        """Test successful health check."""
        mock_isp_client(health_ok=True)

        client = ISPClient()
        result = client.health_check()

        assert result is not None

    def test_health_check_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test health check failure."""
        mock_session = MockISPSession()
        mock_session.set_response("GET", "_health", MockISPResponse(503, {"status": "unavailable"}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()

        with pytest.raises(Exception):
            client.health_check()


class TestISPClientIndexOperations:
    """Tests for ISPClient index operations."""

    def test_index_exists_true(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test index_exists returns True when index exists."""
        mock_session = MockISPSession()
        mock_session.set_response("GET", "aliases", MockISPResponse(200, [{"alias": "test-index"}]))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.index_exists("test-index")

        assert result is True

    def test_index_exists_false(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test index_exists returns False when index doesn't exist."""
        mock_session = MockISPSession()
        mock_session.set_response(
            "GET",
            "aliases",
            MockISPResponse(200, []),  # Empty list
        )

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.index_exists("nonexistent-index")

        assert result is False

    def test_create_index_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful index creation."""
        mock_session = MockISPSession()
        mock_session.set_response("PUT", "test-index", MockISPResponse(200, {"acknowledged": True}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.create_index(
            index_name="test-index",
            mappings={"properties": {"field": {"type": "text"}}},
        )

        assert result["acknowledged"] is True

    def test_create_index_with_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test index creation with settings."""
        mock_session = MockISPSession()
        mock_session.set_response("PUT", "test-index", MockISPResponse(200, {"acknowledged": True}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.create_index(
            index_name="test-index",
            mappings={"properties": {}},
            settings={"number_of_shards": 1},
        )

        assert result["acknowledged"] is True

    def test_delete_index_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful index deletion."""
        mock_session = MockISPSession()
        mock_session.set_response("DELETE", "test-index", MockISPResponse(200, {"acknowledged": True}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.delete_index("test-index")

        assert result["acknowledged"] is True


class TestISPClientDocumentOperations:
    """Tests for ISPClient document operations."""

    def test_index_document_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful document indexing."""
        mock_session = MockISPSession()
        mock_session.set_response("PUT", "_create", MockISPResponse(200, {"_id": "123", "result": "created"}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.index_document(
            index_name="test-index",
            doc_id="123",
            document={"field": "value"},
        )

        assert result["_id"] == "123"

    def test_index_document_upsert(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test document upsert mode."""
        mock_session = MockISPSession()
        mock_session.set_response("PUT", "_doc", MockISPResponse(200, {"_id": "123", "result": "updated"}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.index_document(
            index_name="test-index",
            doc_id="123",
            document={"field": "updated_value"},
            upsert=True,
        )

        assert result["result"] == "updated"

    def test_search_documents(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test document search."""
        mock_session = MockISPSession()
        mock_session.set_response(
            "POST",
            "_search",
            MockISPResponse(
                200,
                {
                    "hits": {
                        "total": {"value": 1},
                        "hits": [{"_id": "123", "_source": {"field": "value"}}],
                    }
                },
            ),
        )

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        result = client.search(
            index_name="test-index",
            query={"query": {"match_all": {}}},
        )

        assert result["hits"]["total"]["value"] == 1


class TestISPClientBulkIndex:
    """Tests for ISPClient.bulk_index_documents method."""

    def test_bulk_index_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful bulk indexing."""
        mock_session = MockISPSession()
        # Set up response for individual document indexing
        mock_session.set_response("PUT", "_doc", MockISPResponse(200, {"result": "created"}))

        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        documents = [
            {"id": "1", "field": "value1"},
            {"id": "2", "field": "value2"},
        ]

        result = client.bulk_index_documents(
            index_name="test-index",
            documents=documents,
            id_field="id",
            upsert=True,
        )

        assert result["total"] == 2
        assert result["success"] == 2
        assert result["errors"] == 0

    def test_bulk_index_missing_id_field(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test bulk indexing with missing id field."""
        mock_session = MockISPSession()
        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        client = ISPClient()
        documents = [
            {"field": "value1"},  # Missing 'id' field
            {"id": "2", "field": "value2"},
        ]

        result = client.bulk_index_documents(
            index_name="test-index",
            documents=documents,
            id_field="id",
        )

        assert result["total"] == 2
        assert result["errors"] == 1
        assert "missing 'id' field" in result["error_details"][0]


class TestCreateISPClientFromEnv:
    """Tests for create_isp_client_from_env factory function."""

    def test_create_from_env_local_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test creating client in local mode."""
        monkeypatch.setenv("TENANT_ID", "test-tenant")
        monkeypatch.setenv("LOCAL_MODE", "true")

        client = create_isp_client_from_env()

        assert client.base_url == "http://localhost:3000"
        assert client.internal_token is None

    def test_create_from_env_with_isp_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test creating client with custom ISP URL."""
        monkeypatch.setenv("TENANT_ID", "test-tenant")
        monkeypatch.setenv("ISP_API_URL", "https://custom-isp.example.com")
        monkeypatch.setenv("LOCAL_MODE", "true")

        client = create_isp_client_from_env()

        assert client.base_url == "https://custom-isp.example.com"

    def test_create_from_env_missing_tenant_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that missing TENANT_ID raises ValueError."""
        # TENANT_ID is cleared by clean_environment fixture

        with pytest.raises(ValueError, match="TENANT_ID environment variable is required"):
            create_isp_client_from_env()

    def test_create_from_env_with_direct_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test creating client with direct M2M token."""
        monkeypatch.setenv("TENANT_ID", "test-tenant")
        monkeypatch.setenv("M2M_INTERNAL_TOKEN", "direct-token")

        client = create_isp_client_from_env()

        assert client.internal_token == "direct-token"
