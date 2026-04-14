"""Unit tests for GeminiClient."""

from pathlib import Path
from typing import Any

import pytest
from common.gemini import (
    GeminiClient,
    analyze_images_with_structured_output,
    generate_embeddings_batch,
)

# Import mock fixtures


class TestGeminiClientInit:
    """Tests for GeminiClient initialization."""

    def test_init_default_values(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test initialization with default values."""
        mock_gemini_client()

        client = GeminiClient(model_name="gemini-2.0-flash")

        assert client.model_name == "gemini-2.0-flash"
        assert client.location == "us-central1"
        assert client.temperature == 0.0
        assert client.seed == 42

    def test_init_custom_values(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test initialization with custom values."""
        mock_gemini_client()

        client = GeminiClient(
            model_name="gemini-pro",
            location="asia-northeast1",
            temperature=0.5,
            seed=123,
        )

        assert client.model_name == "gemini-pro"
        assert client.location == "asia-northeast1"
        assert client.temperature == 0.5
        assert client.seed == 123

    def test_client_lazy_initialization(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test that client is lazily initialized."""
        mocks = mock_gemini_client()

        client = GeminiClient(model_name="gemini-2.0-flash")

        # Client should not be initialized yet
        assert client._client is None
        # vertexai.init should not have been called yet
        mocks["init"].assert_not_called()


class TestGeminiClientGenerate:
    """Tests for GeminiClient.generate_structured_content method."""

    def test_generate_structured_content_success(
        self,
        mock_gemini_client,  # noqa: F811
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test successful structured content generation."""
        expected_response = {
            "cause_unit": "テストユニット1",
            "failure_mode": "摩耗",
        }
        mock_gemini_client(generate_response=expected_response)

        client = GeminiClient(model_name="gemini-2.0-flash")
        result = client.generate_structured_content(
            contents=["Test content"],
            response_schema=sample_response_schema,
        )

        assert result == expected_response
        assert result["cause_unit"] == "テストユニット1"

    def test_generate_with_system_instruction(
        self,
        mock_gemini_client,  # noqa: F811
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test generation with system instruction."""
        mock_gemini_client(generate_response={"cause_unit": "unit"})

        client = GeminiClient(model_name="gemini-2.0-flash")
        result = client.generate_structured_content(
            contents=["Test content"],
            response_schema=sample_response_schema,
            system_instruction="You are a helpful assistant.",
        )

        assert result is not None

    def test_generate_initializes_client(
        self,
        mock_gemini_client,  # noqa: F811
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test that generate initializes the client lazily."""
        mocks = mock_gemini_client(generate_response={})

        client = GeminiClient(model_name="gemini-2.0-flash")
        assert client._client is None

        client.generate_structured_content(
            contents=["Test"],
            response_schema=sample_response_schema,
        )

        # After generation, client should be initialized
        mocks["init"].assert_called_once()


class TestAnalyzeImagesWithStructuredOutput:
    """Tests for analyze_images_with_structured_output function."""

    def test_analyze_images_success(
        self,
        mock_gemini_client,  # noqa: F811
        temp_image_files: list[Path],
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test successful image analysis."""
        expected_response = {
            "cause_unit": "テストユニット1",
            "cause_part": ["部品A"],
            "failure_mode": "摩耗",
        }
        mock_gemini_client(generate_response=expected_response)

        result = analyze_images_with_structured_output(
            image_paths=temp_image_files,
            system_instruction="Analyze defects",
            response_schema=sample_response_schema,
            model_name="gemini-2.0-flash",
        )

        assert result == expected_response

    def test_analyze_images_with_provided_client(
        self,
        mock_gemini_client,  # noqa: F811
        temp_image_files: list[Path],
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test image analysis with provided client."""
        expected_response = {"cause_unit": "provided"}
        mock_gemini_client(generate_response=expected_response)

        client = GeminiClient(model_name="gemini-2.0-flash")
        result = analyze_images_with_structured_output(
            image_paths=temp_image_files,
            system_instruction="Analyze defects",
            response_schema=sample_response_schema,
            model_name="gemini-2.0-flash",
            client=client,
        )

        assert result["cause_unit"] == "provided"

    def test_analyze_handles_png_and_jpeg(
        self,
        mock_gemini_client,  # noqa: F811
        tmp_path: Path,
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test that both PNG and JPEG files are handled."""
        mock_gemini_client(generate_response={})

        # Create test files with different extensions
        png_file = tmp_path / "test.png"
        jpeg_file = tmp_path / "test.jpg"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        jpeg_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        # Should not raise any errors
        result = analyze_images_with_structured_output(
            image_paths=[png_file, jpeg_file],
            system_instruction="Analyze",
            response_schema=sample_response_schema,
            model_name="gemini-2.0-flash",
        )

        assert result is not None


class TestGenerateEmbeddingsBatch:
    """Tests for generate_embeddings_batch function."""

    def test_generate_embeddings_success(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test successful embedding generation."""
        expected_embeddings = [[0.1] * 768, [0.2] * 768]
        mock_gemini_client(embed_response=expected_embeddings)

        texts = ["First text", "Second text"]
        embeddings, summary = generate_embeddings_batch(
            texts=texts,
            model_name="text-embedding-004",
            dimensionality=768,
        )

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 768
        assert summary["embedded"] == 2
        assert summary["skipped_empty"] == 0
        assert summary["errors"] == 0
        assert summary["skipped_details"] == []
        assert summary["error_details"] == []

    def test_generate_embeddings_empty_list(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test embedding generation with empty list."""
        mock_gemini_client()

        embeddings, summary = generate_embeddings_batch(
            texts=[],
            model_name="text-embedding-004",
        )

        assert embeddings == []
        assert summary["total"] == 0
        assert summary["skipped_details"] == []
        assert summary["error_details"] == []

    def test_generate_embeddings_empty_text_returns_empty(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test that empty text returns empty embedding."""
        mock_gemini_client(embed_response=[[0.1] * 768])

        embeddings, summary = generate_embeddings_batch(
            texts=["", "  "],  # Empty and whitespace-only
            model_name="text-embedding-004",
        )

        # Empty texts should return empty embeddings
        assert embeddings[0] == []
        assert embeddings[1] == []
        assert summary["embedded"] == 0
        assert summary["skipped_empty"] == 2
        assert summary["errors"] == 0
        assert len(summary["skipped_details"]) == 2
        assert summary["error_details"] == []

    def test_generate_embeddings_with_custom_params(
        self,
        mock_gemini_client,  # noqa: F811
    ) -> None:
        """Test embedding generation with custom parameters."""
        mock_gemini_client(embed_response=[[0.1] * 256])

        embeddings, summary = generate_embeddings_batch(
            texts=["Test"],
            model_name="custom-embedding-model",
            location="asia-northeast1",
            task_type="RETRIEVAL_QUERY",
            dimensionality=256,
        )

        assert len(embeddings) == 1
        assert summary["embedded"] == 1


class TestGeminiClientRetry:
    """Tests for retry logic in GeminiClient."""

    def test_retry_on_rate_limit(
        self,
        mock_gemini_client,  # noqa: F811
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test that rate limit errors trigger retry.

        Note: Full retry testing requires integration tests as we need
        to verify actual retry behavior. This test verifies the error
        is raised properly.
        """
        import google.api_core.exceptions

        error = google.api_core.exceptions.ResourceExhausted("Rate limit")
        mock_gemini_client(generate_error=error)

        client = GeminiClient(
            model_name="gemini-2.0-flash",
            max_retries=1,  # Fail fast for testing
            retry_min_wait=0.1,
            retry_max_wait=0.1,
        )

        with pytest.raises(Exception):
            client.generate_structured_content(
                contents=["Test"],
                response_schema=sample_response_schema,
            )

    def test_non_retriable_error_not_retried(
        self,
        mock_gemini_client,  # noqa: F811
        sample_response_schema: dict[str, Any],
    ) -> None:
        """Test that non-retriable errors are not retried."""
        error = ValueError("Invalid input")
        mock_gemini_client(generate_error=error)

        client = GeminiClient(model_name="gemini-2.0-flash")

        with pytest.raises(ValueError, match="Invalid input"):
            client.generate_structured_content(
                contents=["Test"],
                response_schema=sample_response_schema,
            )
