"""Mock classes for Gemini client testing."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest


class MockEmbedding:
    """Mock embedding result."""

    def __init__(self, values: list[float]):
        self.values = values


class MockEmbedResult:
    """Mock embedding response."""

    def __init__(self, embeddings: list[list[float]]):
        self.embeddings = [MockEmbedding(e) for e in embeddings]


class MockGenerateResponse:
    """Mock Gemini generate content response."""

    def __init__(self, response_dict: dict[str, Any]):
        self._response = response_dict

    @property
    def text(self) -> str:
        """Return JSON string of the response."""
        return json.dumps(self._response)


class MockGenaiModels:
    """Mock genai.Client.models."""

    def __init__(
        self,
        generate_response: dict[str, Any] | None = None,
        embed_response: list[list[float]] | None = None,
        generate_error: Exception | None = None,
        embed_error: Exception | None = None,
    ):
        self._generate_response = generate_response or {}
        self._embed_response = embed_response or [[0.1] * 768]
        self._generate_error = generate_error
        self._embed_error = embed_error

    def generate_content(self, **kwargs: Any) -> MockGenerateResponse:
        """Generate content."""
        if self._generate_error:
            raise self._generate_error
        return MockGenerateResponse(self._generate_response)

    def embed_content(self, **kwargs: Any) -> MockEmbedResult:
        """Generate embeddings."""
        if self._embed_error:
            raise self._embed_error
        return MockEmbedResult(self._embed_response)


class MockGenaiClient:
    """Mock genai.Client."""

    def __init__(
        self,
        generate_response: dict[str, Any] | None = None,
        embed_response: list[list[float]] | None = None,
        generate_error: Exception | None = None,
        embed_error: Exception | None = None,
    ):
        self.models = MockGenaiModels(
            generate_response,
            embed_response,
            generate_error,
            embed_error,
        )


@pytest.fixture
def mock_gemini_client(monkeypatch: pytest.MonkeyPatch):
    """Fixture to mock Gemini client.

    Returns a factory function to create configured mocks.

    Example:
        def test_generate(mock_gemini_client):
            mocks = mock_gemini_client(
                generate_response={"cause_unit": "テスト"}
            )

            from common.gemini import GeminiClient
            client = GeminiClient(model_name="gemini-2.0-flash")
            result = client.generate_structured_content(...)

    """

    def _create_mock(
        generate_response: dict[str, Any] | None = None,
        embed_response: list[list[float]] | None = None,
        generate_error: Exception | None = None,
        embed_error: Exception | None = None,
    ) -> dict[str, Any]:
        # Reset VertexAIInitializer singleton for each test
        from common.gemini.vertex_ai import VertexAIInitializer

        VertexAIInitializer._instance = None

        # Mock vertexai.init at the vertex_ai module where it's called
        mock_init = MagicMock()
        monkeypatch.setattr("common.gemini.vertex_ai.vertexai.init", mock_init)

        # Mock google.auth.default at the vertex_ai module (shared initialization)
        mock_creds = MagicMock()
        mock_default = MagicMock(return_value=(mock_creds, "test-project"))
        # Patch at vertex_ai module where it's imported
        monkeypatch.setattr("common.gemini.vertex_ai.default", mock_default)

        # Create mock client
        mock_client = MockGenaiClient(
            generate_response,
            embed_response,
            generate_error,
            embed_error,
        )

        # Mock genai.Client constructor at all modules where it's used
        mock_client_class = MagicMock(return_value=mock_client)
        monkeypatch.setattr("common.gemini.client.genai.Client", mock_client_class)
        monkeypatch.setattr("common.gemini.embeddings.genai.Client", mock_client_class)

        return {
            "client": mock_client,
            "client_class": mock_client_class,
            "init": mock_init,
            "default": mock_default,
            "credentials": mock_creds,
        }

    return _create_mock


@pytest.fixture
def mock_gemini_rate_limit_error():
    """Create a rate limit error for testing retry logic."""
    import google.api_core.exceptions

    return google.api_core.exceptions.ResourceExhausted("Rate limit exceeded")


@pytest.fixture
def mock_gemini_service_unavailable_error():
    """Create a service unavailable error for testing retry logic."""
    import google.api_core.exceptions

    return google.api_core.exceptions.ServiceUnavailable("Service unavailable")
