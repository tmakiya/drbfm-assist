"""Gemini API client for structured content generation."""

import json
import threading
from typing import Any, Optional

from google import genai
from loguru import logger

from .retry import create_retry_decorator
from .vertex_ai import get_vertex_ai_credentials


class GeminiClient:
    """Gemini API client with structured output and retry support."""

    def __init__(
        self,
        model_name: str,
        location: str = "us-central1",
        temperature: float = 0.0,
        seed: int = 42,
        max_retries: int = 4,
        retry_min_wait: float = 10.0,
        retry_max_wait: float = 80.0,
    ):
        """Initialize Gemini client.

        Args:
            model_name: Gemini model name
            location: GCP location
            temperature: Generation temperature
            seed: Random seed for reproducibility
            max_retries: Maximum retry attempts
            retry_min_wait: Minimum wait between retries (seconds)
            retry_max_wait: Maximum wait between retries (seconds)

        """
        self.model_name = model_name
        self.location = location
        self.temperature = temperature
        self.seed = seed
        self.max_retries = max_retries
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait

        self._client: Optional[genai.Client] = None
        self._lock = threading.Lock()

    def _get_client(self) -> genai.Client:
        """Get or create Gemini client (thread-safe lazy initialization)."""
        if self._client is None:
            with self._lock:
                if self._client is None:
                    # Use shared initialization
                    get_vertex_ai_credentials(self.location)
                    self._client = genai.Client(vertexai=True, location=self.location)
                    logger.debug(f"Gemini client created: model={self.model_name}")
        return self._client

    def _generate(
        self,
        contents,
        extra_config: dict[str, Any],
        system_instruction: Optional[str] = None,
    ):
        """Generate content with retry logic.

        Args:
            contents: Input contents
            extra_config: Additional config (e.g., response_schema)
            system_instruction: Optional system instruction

        Returns:
            API response

        """
        retry_decorator = create_retry_decorator(
            max_retries=self.max_retries,
            min_wait=self.retry_min_wait,
            max_wait=self.retry_max_wait,
            operation_name=f"generate_content({self.model_name})",
        )

        @retry_decorator
        def _call():
            config_dict = {"temperature": self.temperature, "seed": self.seed, **extra_config}
            if system_instruction:
                config_dict["system_instruction"] = system_instruction

            return self._get_client().models.generate_content(
                model=self.model_name,
                contents=contents,
                config=genai.types.GenerateContentConfig(**config_dict),
            )

        return _call()

    def generate_structured_content(
        self,
        contents,
        response_schema: dict[str, Any],
        system_instruction: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate structured content using JSON schema.

        Args:
            contents: Input contents
            response_schema: JSON schema for response
            system_instruction: Optional system instruction

        Returns:
            Parsed JSON response

        Raises:
            Exception: If generation or JSON parsing fails

        """
        extra_config = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }

        response = self._generate(contents, extra_config, system_instruction)

        try:
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response.text[:500]}")
            raise
