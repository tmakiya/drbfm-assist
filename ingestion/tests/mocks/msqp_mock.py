"""Mock classes for MSQP (Trino) client testing."""

from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest


class MockTrinoCursor:
    """Mock Trino cursor."""

    def __init__(self, results: pl.DataFrame | None = None):
        self._results = results if results is not None else pl.DataFrame()
        self._description: list[tuple[str, Any, ...]] | None = None
        self._executed = False

    def execute(self, sql: str) -> None:
        """Execute a SQL query."""
        self._executed = True
        # Set description based on DataFrame columns
        if not self._results.is_empty():
            self._description = [(col, None, None, None, None, None, None) for col in self._results.columns]
        else:
            self._description = []

    @property
    def description(self) -> list[tuple[str, Any, ...]] | None:
        """Return column descriptions."""
        return self._description

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Fetch all results."""
        if self._results.is_empty():
            return []
        return [tuple(row.values()) for row in self._results.iter_rows(named=True)]


class MockTrinoConnection:
    """Mock Trino database connection."""

    def __init__(self, query_results: pl.DataFrame | None = None):
        self.query_results = query_results
        self._closed = False
        self._cursor: MockTrinoCursor | None = None

    def cursor(self) -> MockTrinoCursor:
        """Get a cursor for executing queries."""
        self._cursor = MockTrinoCursor(self.query_results)
        return self._cursor

    def close(self) -> None:
        """Close the connection."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self._closed


@pytest.fixture
def mock_msqp_client(monkeypatch: pytest.MonkeyPatch, valid_jwt_token: str):
    """Fixture to mock MSQP client dependencies.

    Returns a factory function to create configured mocks.

    Example:
        def test_query(mock_msqp_client):
            expected_df = pl.DataFrame({"col": [1, 2, 3]})
            mocks = mock_msqp_client(query_result=expected_df)

            client = MSQPClient(...)
            result = client.query("SELECT * FROM test")

            assert len(result) == 3

    """

    def _create_mock(
        query_result: pl.DataFrame | None = None,
        token_response: dict[str, Any] | None = None,
        token_status_code: int = 200,
        should_fail_connection: bool = False,
    ) -> dict[str, Any]:
        # Mock token acquisition
        mock_response = MagicMock()
        mock_response.status_code = token_status_code
        if token_response is None:
            token_response = {"access_token": valid_jwt_token}
        mock_response.json.return_value = token_response

        mock_post = MagicMock(return_value=mock_response)
        monkeypatch.setattr("requests.post", mock_post)

        # Mock Trino connection
        if should_fail_connection:
            mock_connect = MagicMock(side_effect=Exception("Connection failed"))
        else:
            mock_conn = MockTrinoConnection(query_result)
            mock_connect = MagicMock(return_value=mock_conn)

        # Mock at the location where it's imported in the client module
        monkeypatch.setattr("common.msqp.client.connect", mock_connect)

        return {
            "post": mock_post,
            "connect": mock_connect,
            "connection": mock_conn if not should_fail_connection else None,
            "token": valid_jwt_token,
        }

    return _create_mock


@pytest.fixture
def mock_msqp_token_failure(monkeypatch: pytest.MonkeyPatch):
    """Fixture to mock MSQP token acquisition failure."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": "Unauthorized"}

    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr("requests.post", mock_post)

    return mock_post
