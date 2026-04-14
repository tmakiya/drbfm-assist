"""Mock classes for M2M Token Issuer client testing."""

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_m2m_token_issuer(
    monkeypatch: pytest.MonkeyPatch,
    valid_m2m_jwt_token: str,
    mock_env_dev: dict[str, str],
):
    """Fixture to mock M2M Token Issuer client.

    Example:
        def test_token_acquisition(mock_m2m_token_issuer):
            mocks = mock_m2m_token_issuer

            from common.m2m_token_issuer import M2MTokenIssuerClient
            client = M2MTokenIssuerClient.from_env()
            token = client.get_token()

            assert token == mocks["token"]

    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"access_token": valid_m2m_jwt_token}
    mock_response.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.post.return_value = mock_response
    mock_session.trust_env = True

    mock_session_class = MagicMock(return_value=mock_session)
    monkeypatch.setattr("requests.Session", mock_session_class)

    return {
        "session": mock_session,
        "session_class": mock_session_class,
        "response": mock_response,
        "token": valid_m2m_jwt_token,
    }


@pytest.fixture
def mock_m2m_token_failure(monkeypatch: pytest.MonkeyPatch):
    """Fixture to mock M2M token acquisition failure.

    Example:
        def test_token_failure(mock_m2m_token_failure):
            from common.m2m_token_issuer import M2MTokenIssuerClient

            with pytest.raises(Exception):
                client = M2MTokenIssuerClient.from_env()
                client.get_token()

    """
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": "invalid_client"}
    mock_response.text = "Invalid client credentials"

    def raise_for_status():
        from requests import HTTPError

        raise HTTPError("401 Client Error: Unauthorized")

    mock_response.raise_for_status = raise_for_status

    mock_session = MagicMock()
    mock_session.post.return_value = mock_response
    mock_session.trust_env = True

    mock_session_class = MagicMock(return_value=mock_session)
    monkeypatch.setattr("requests.Session", mock_session_class)

    return {
        "session": mock_session,
        "response": mock_response,
    }


@pytest.fixture
def mock_m2m_token_with_custom_claims(monkeypatch: pytest.MonkeyPatch):
    """Fixture to create M2M token with custom claims.

    Returns a factory function to create tokens with specific claims.

    Example:
        def test_custom_claims(mock_m2m_token_with_custom_claims):
            token = mock_m2m_token_with_custom_claims(
                tenant_id="custom-tenant",
                extra_claims={"role": "admin"}
            )

    """
    import base64
    import json

    def _create_token(
        tenant_id: str = "test-tenant-123",
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        )

        claims = {
            "https://zoolake.jp/claims/tenantId": tenant_id,
            "sub": "m2m-client",
            "exp": 9999999999,
        }
        if extra_claims:
            claims.update(extra_claims)

        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")

        signature = "mock_signature"

        return f"{header}.{payload}.{signature}"

    return _create_token
