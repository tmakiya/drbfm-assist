"""Gemini API client with structured processing and retry logic"""

import json
import threading
from typing import Any, Dict, Optional

import google.api_core.exceptions
import vertexai
from google import genai
from google.auth import default
import structlog

logger = structlog.stdlib.get_logger(__name__)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Define retriable exceptions
RETRIABLE_EXCEPTIONS = (
    google.api_core.exceptions.ServiceUnavailable,
    google.api_core.exceptions.TooManyRequests,
    google.api_core.exceptions.DeadlineExceeded,
    google.api_core.exceptions.InternalServerError,
    google.api_core.exceptions.ResourceExhausted,
    google.api_core.exceptions.Aborted,
    ConnectionError,
    genai.errors.ClientError,  # Handle 429 RESOURCE_EXHAUSTED from genai
)


class GeminiClient:
    """Gemini API client with common configuration and structured output support"""

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        location: str = "us-central1",
        temperature: float = 0.0,
        seed: int = 42,
        max_retries: int = 5,
        retry_min_wait: float = 1.0,
        retry_max_wait: float = 60.0,
        retry_multiplier: float = 1.0,
    ):
        """Initialize Gemini client with retry configuration

        Args:
            model_name: Gemini model name to use
            location: GCP location for Vertex AI
            temperature: Generation temperature
            seed: Random seed for reproducible results
            max_retries: Maximum number of retry attempts
            retry_min_wait: Minimum wait time between retries (seconds)
            retry_max_wait: Maximum wait time between retries (seconds)
            retry_multiplier: Exponential backoff multiplier

        """
        self.model_name = model_name
        self.location = location
        self.temperature = temperature
        self.seed = seed

        # Retry configuration
        self.max_retries = max_retries
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait
        self.retry_multiplier = retry_multiplier

        self._client: Optional[genai.Client] = None
        self._project_id: Optional[str] = None
        self._credentials = None
        self._client_lock = threading.Lock()

    def _initialize_vertex_ai(self) -> None:
        """Initialize Vertex AI with authentication"""
        if self._credentials is None or self._project_id is None:
            logger.info("Initializing Vertex AI authentication")
            self._credentials, self._project_id = default()

            vertexai.init(
                project=self._project_id,
                location=self.location,
                credentials=self._credentials,
            )
            logger.info("Vertex AI initialized", project=self._project_id)

    def _get_client(self) -> genai.Client:
        """Get or create Gemini client with thread-safe lazy initialization"""
        if self._client is None:
            with self._client_lock:
                # Double-check locking pattern to prevent race conditions
                if self._client is None:
                    self._initialize_vertex_ai()
                    self._client = genai.Client(vertexai=True, location=self.location)
                    logger.info("Gemini client created", model=self.model_name)

        return self._client

    def _generate_content(
        self,
        prompt: str,
        extra_config: Dict[str, Any],
        **generation_config_overrides,
    ):
        """Generate content with retry logic

        Args:
            prompt: Input prompt for generation
            extra_config: Additional configuration (e.g., JSON schema)
            **generation_config_overrides: Override default generation config

        Returns:
            Raw API response

        Raises:
            Exception: If generation fails after all retries

        """
        # Create a retry decorator with instance-specific configuration
        retry_decorator = retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=self.retry_multiplier,
                min=self.retry_min_wait,
                max=self.retry_max_wait,
            ),
            retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
        )

        @retry_decorator
        def _generate_with_retry():
            client = self._get_client()

            # Build generation config
            generation_config = {
                "temperature": self.temperature,
                "seed": self.seed,
            }

            # Apply extra config and overrides
            generation_config.update(extra_config)
            generation_config.update(generation_config_overrides)

            config = genai.types.GenerateContentConfig(**generation_config)

            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            return response

        return _generate_with_retry()

    def generate_structured_content(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        **generation_config_overrides,
    ) -> Dict[str, Any]:
        """Generate structured content using JSON schema

        Args:
            prompt: Input prompt for generation
            response_schema: JSON schema for structured output
            **generation_config_overrides: Override default generation config

        Returns:
            Parsed JSON response as dictionary

        Raises:
            Exception: If generation or parsing fails

        """
        try:
            extra_config = {
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            }

            response = self._generate_content(
                prompt, extra_config, **generation_config_overrides
            )

            # Parse JSON response
            result = json.loads(response.text)

            return result

        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response", error=str(e))
            raise Exception(f"Failed to parse JSON response: {str(e)}") from e

    def generate_content(self, prompt: str, **generation_config_overrides) -> str:
        """Generate simple text content

        Args:
            prompt: Input prompt for generation
            **generation_config_overrides: Override default generation config

        Returns:
            Generated text content

        Raises:
            Exception: If generation fails

        """
        response = self._generate_content(prompt, {}, **generation_config_overrides)
        return response.text

    @property
    def is_initialized(self) -> bool:
        """Check if the client has been initialized"""
        return self._client is not None

    def initialize(self) -> None:
        """Explicitly initialize the client (optional, for eager initialization)"""
        self._get_client()

    @property
    def project_id(self) -> Optional[str]:
        """Get current project ID"""
        if self._project_id is None:
            self._initialize_vertex_ai()
        return self._project_id
