"""Vertex AI embeddings client with enhanced flexibility and error handling"""

import time
from typing import Callable, Dict, List, Optional, Union

import structlog
import vertexai
from google import genai
from google.auth import default
from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    InternalServerError,
    ResourceExhausted,
    ServiceUnavailable,
    TooManyRequests,
)
from tqdm import tqdm

logger = structlog.stdlib.get_logger(__name__)


RETRIABLE_EXCEPTIONS = (
    ServiceUnavailable,
    TooManyRequests,
    DeadlineExceeded,
    InternalServerError,
    ResourceExhausted,
    Aborted,
    ConnectionError,
)


class EmbeddingException(Exception):
    """Custom exception for embedding generation errors"""

    pass


class VertexAIEmbedder:
    """Vertex AI embeddings client with enhanced flexibility"""

    def __init__(
        self,
        config: Union[Dict[str, str], object] = None,
        logger_func: Optional[Callable] = None,
        enable_progress: bool = True,
        model_name: str = "gemini-embedding-001",
        location: str = "us-central1",
        task_type: str = "RETRIEVAL_QUERY",
        dimensionality: int = 3072,
    ):
        """Initialize Vertex AI embedder

        Args:
            config: Configuration object (for compatibility, not used)
            logger_func: Custom logger function (defaults to structlog logger)
            enable_progress: Whether to show progress bars
            model_name: Embedding model name (default: gemini-embedding-001)
            location: GCP region (default: us-central1)
            task_type: Task type for embedding (RETRIEVAL_QUERY for search,
                      RETRIEVAL_DOCUMENT for indexing)
            dimensionality: Output embedding dimension (default: 3072)
        """
        self.logger = logger_func or logger
        self.enable_progress = enable_progress
        self.model_name = model_name
        self.location = location
        self.task_type = task_type
        self.dimensionality = dimensionality
        self._client: genai.Client | None = None
        self._initialized = False

    def _initialize(self) -> None:
        """Initialize Vertex AI with authentication."""
        if not self._initialized:
            credentials, project_id = default()
            vertexai.init(
                project=project_id,
                location=self.location,
                credentials=credentials,
            )
            self._client = genai.Client(vertexai=True, location=self.location)
            self._initialized = True
            self.logger.info(
                "Vertex AI initialized",
                project=project_id,
                location=self.location,
            )

    def generate_embedding(
        self, text: str, retry_count: int = 5, base_wait_time: float = 1.0
    ) -> Optional[List[float]]:
        """Generate embedding for given text with configurable retry logic

        Args:
            text: Text to generate embedding for
            retry_count: Number of retry attempts
            base_wait_time: Base wait time for exponential backoff

        Returns:
            Embedding vector or None if failed

        Raises:
            EmbeddingException: If all retries fail and exceptions are enabled
        """
        if not text or not text.strip():
            return None

        self._initialize()

        for attempt in range(retry_count):
            try:
                result = self._client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=genai.types.EmbedContentConfig(
                        task_type=self.task_type,
                        output_dimensionality=self.dimensionality,
                    ),
                )
                return result.embeddings[0].values
            except RETRIABLE_EXCEPTIONS as e:
                wait_time = base_wait_time * (2**attempt)
                self.logger.warning(
                    "Embedding generation failed",
                    attempt=attempt + 1,
                    retry_count=retry_count,
                    error=str(e),
                )

                if attempt < retry_count - 1:
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        "Failed to generate embedding after retries",
                        retry_count=retry_count,
                        text_preview=text[:100],
                    )
                    return None
            except Exception as e:
                self.logger.error("Unexpected error generating embedding", error=str(e))
                return None

        return None

    def generate_embeddings_batch(
        self,
        texts: List[str],
        retry_count: int = 5,
        progress_desc: str = "Generating embeddings",
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts

        Args:
            texts: List of texts to generate embeddings for
            retry_count: Number of retry attempts per text
            progress_desc: Description for progress bar

        Returns:
            List of embedding vectors (None for failed generations)
        """
        if not texts:
            return []

        self._initialize()

        embeddings = []

        # Process texts with progress bar
        iterator = texts
        if self.enable_progress:
            iterator = tqdm(iterator, desc=progress_desc)

        for text in iterator:
            embedding = self.generate_embedding(text, retry_count=retry_count)
            embeddings.append(embedding)

        successful_count = sum(1 for e in embeddings if e is not None)
        self.logger.info(
            "Embeddings generated",
            successful=successful_count,
            total=len(embeddings),
        )

        return embeddings

    def get_embedding_stats(
        self, embeddings: List[Optional[List[float]]]
    ) -> Dict[str, int]:
        """Get statistics about embedding generation results"""
        total = len(embeddings)
        successful = sum(1 for e in embeddings if e is not None)
        failed = total - successful

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0.0,
        }
