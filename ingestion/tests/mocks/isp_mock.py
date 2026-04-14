"""Mock classes for ISP client testing."""

from typing import Any
from unittest.mock import MagicMock

import pytest


class MockISPResponse:
    """Mock HTTP response for ISP."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str | None = None,
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text if text is not None else str(json_data)
        self.ok = 200 <= status_code < 300

    def json(self) -> dict[str, Any]:
        """Return JSON data."""
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise an exception for 4xx/5xx status codes."""
        if self.status_code >= 400:
            from requests import HTTPError

            raise HTTPError(f"HTTP {self.status_code}: {self.text}")


class MockISPSession:
    """Mock requests.Session for ISP client."""

    def __init__(self):
        self.trust_env = True
        self.headers: dict[str, str] = {}
        self._responses: dict[str, MockISPResponse] = {}
        self._default_response = MockISPResponse(200, {"acknowledged": True})
        self._call_history: list[dict[str, Any]] = []

    def set_response(
        self,
        method: str,
        url_pattern: str,
        response: MockISPResponse,
    ) -> None:
        """Set a specific response for method and URL pattern."""
        self._responses[f"{method}:{url_pattern}"] = response

    def _get_response(self, method: str, url: str) -> MockISPResponse:
        """Get the response for a given method and URL."""
        for key, response in self._responses.items():
            m, pattern = key.split(":", 1)
            if m == method and pattern in url:
                return response
        return self._default_response

    def _record_call(self, method: str, url: str, **kwargs: Any) -> None:
        """Record a call for verification."""
        self._call_history.append(
            {
                "method": method,
                "url": url,
                **kwargs,
            }
        )

    def get(self, url: str, **kwargs: Any) -> MockISPResponse:
        """Mock GET request."""
        self._record_call("GET", url, **kwargs)
        return self._get_response("GET", url)

    def post(self, url: str, **kwargs: Any) -> MockISPResponse:
        """Mock POST request."""
        self._record_call("POST", url, **kwargs)
        return self._get_response("POST", url)

    def put(self, url: str, **kwargs: Any) -> MockISPResponse:
        """Mock PUT request."""
        self._record_call("PUT", url, **kwargs)
        return self._get_response("PUT", url)

    def delete(self, url: str, **kwargs: Any) -> MockISPResponse:
        """Mock DELETE request."""
        self._record_call("DELETE", url, **kwargs)
        return self._get_response("DELETE", url)

    def head(self, url: str, **kwargs: Any) -> MockISPResponse:
        """Mock HEAD request."""
        self._record_call("HEAD", url, **kwargs)
        return self._get_response("HEAD", url)

    def get_call_history(self, method: str | None = None) -> list[dict[str, Any]]:
        """Get call history, optionally filtered by method."""
        if method is None:
            return self._call_history
        return [c for c in self._call_history if c["method"] == method]


@pytest.fixture
def mock_isp_session() -> MockISPSession:
    """Fixture to create a mock ISP session."""
    return MockISPSession()


@pytest.fixture
def mock_isp_client(monkeypatch: pytest.MonkeyPatch, mock_env_dev: dict[str, str]):
    """Fixture to mock ISP client dependencies.

    Returns a factory function to create configured mocks.

    Example:
        def test_index(mock_isp_client):
            session = mock_isp_client()
            session.set_response("GET", "_health", MockISPResponse(200, {"status": "ok"}))

            from common.isp import create_isp_client_from_env
            client = create_isp_client_from_env()
            client.health_check()

    """

    def _create_mock(
        health_ok: bool = True,
        index_exists: bool = False,
        bulk_success: bool = True,
    ) -> MockISPSession:
        mock_session = MockISPSession()

        # Set up health check response
        if health_ok:
            mock_session.set_response("GET", "_health", MockISPResponse(200, {"status": "ok"}))
        else:
            mock_session.set_response("GET", "_health", MockISPResponse(503, {"status": "unavailable"}))

        # Set up index exists check
        if index_exists:
            mock_session.set_response("HEAD", "", MockISPResponse(200))
        else:
            mock_session.set_response("HEAD", "", MockISPResponse(404))

        # Set up bulk index response
        if bulk_success:
            mock_session.set_response("POST", "_bulk", MockISPResponse(200, {"errors": False, "items": []}))
        else:
            mock_session.set_response(
                "POST",
                "_bulk",
                MockISPResponse(
                    200, {"errors": True, "items": [{"index": {"error": {"reason": "Test error"}}}]}
                ),
            )

        # Set up index creation response
        mock_session.set_response("PUT", "", MockISPResponse(200, {"acknowledged": True}))

        # Mock requests.Session
        mock_session_class = MagicMock(return_value=mock_session)
        monkeypatch.setattr("requests.Session", mock_session_class)

        return mock_session

    return _create_mock
