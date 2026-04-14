"""Azure OpenAI embeddings client with enhanced flexibility and error handling"""

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Union

from loguru import logger
from openai import (
    APIError,
    APITimeoutError,
    AuthenticationError,
    AzureOpenAI,
    RateLimitError,
)
from tqdm import tqdm


@dataclass
class EmbeddingConfig:
    """Configuration for Azure OpenAI embeddings"""

    endpoint: str
    api_key: str
    api_version: str = "2023-05-15"
    deployment: str = "text-embedding-3-large"


class EmbeddingException(Exception):
    """Custom exception for embedding generation errors"""

    pass


class AzureOpenAIEmbedder:
    """Azure OpenAI embeddings client with enhanced flexibility"""

    def __init__(
        self,
        config: Union[EmbeddingConfig, Dict[str, str], object],
        logger_func: Optional[Callable] = None,
        enable_progress: bool = True,
    ):
        """Initialize Azure OpenAI embedder

        Args:
            config: Configuration object, dictionary, or object with required attributes
            logger_func: Custom logger function (defaults to loguru logger)
            enable_progress: Whether to show progress bars

        """
        self.logger = logger_func or logger
        self.enable_progress = enable_progress

        # Extract configuration
        # self.config = EmbeddingConfig(**config)

        # Initialize client
        self.client = AzureOpenAI()

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
        for attempt in range(retry_count):
            try:
                response = self.client.embeddings.create(input=text, model="text-embedding-3-large")
                return response.data[0].embedding
            except (RateLimitError, APITimeoutError) as e:
                wait_time = base_wait_time * (2**attempt)
                self.logger.warning(f"Embedding generation failed (attempt {attempt + 1}/{retry_count}): {e}")

                if attempt < retry_count - 1:
                    time.sleep(wait_time)
                else:
                    error_msg = f"Failed to generate embedding after {retry_count} attempts: {text[:100]}..."
                    self.logger.error(error_msg)
                    return None
            except AuthenticationError as e:
                self.logger.error(f"Authentication or request error (not retrying): {e}")
                return None
            except APIError as e:
                wait_time = base_wait_time * (2**attempt)
                self.logger.warning(f"API error (attempt {attempt + 1}/{retry_count}): {e}")

                if attempt < retry_count - 1:
                    time.sleep(wait_time)
                else:
                    error_msg = f"Failed to generate embedding after {retry_count} attempts: {text[:100]}..."
                    self.logger.error(error_msg)
                    return None
            except Exception as e:
                self.logger.error(f"Unexpected error generating embedding: {e}")
                return None

    def generate_embeddings_batch(
        self,
        texts: List[str],
        retry_count: int = 5,
        progress_desc: str = "Generating embeddings",
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts using Azure OpenAI batch requests

        Args:
            texts: List of texts to generate embeddings for
            max_workers: Kept for compatibility (not used in batch requests)
            retry_count: Number of retry attempts per batch
            progress_desc: Description for progress bar

        Returns:
            List of embedding vectors (None for failed generations)

        """
        if not texts:
            return []

        # Determine batch size based on model
        model = "text-embedding-3-large"  # default model
        if "ada-002" in model:
            batch_size = 16
        else:
            batch_size = 2048

        embeddings = []
        total_chunks = (len(texts) + batch_size - 1) // batch_size

        # Process texts in chunks
        iterator = range(total_chunks)
        if self.enable_progress:
            iterator = tqdm(iterator, desc=progress_desc)

        for chunk_idx in iterator:
            start_idx = chunk_idx * batch_size
            end_idx = min(start_idx + batch_size, len(texts))
            chunk_texts = texts[start_idx:end_idx]

            chunk_embeddings = self._generate_batch_chunk(chunk_texts, retry_count)
            embeddings.extend(chunk_embeddings)

        successful_count = sum(1 for e in embeddings if e is not None)
        self.logger.info(f"Generated {successful_count}/{len(embeddings)} embeddings successfully")

        return embeddings

    def _generate_batch_chunk(
        self, texts: List[str], retry_count: int = 5, base_wait_time: float = 1.0
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for a chunk of texts using batch request

        Args:
            texts: List of texts for the batch
            retry_count: Number of retry attempts
            base_wait_time: Base wait time for exponential backoff

        Returns:
            List of embedding vectors (None for failed generations)

        """
        for attempt in range(retry_count):
            try:
                response = self.client.embeddings.create(input=texts, model="text-embedding-3-large")
                return [data.embedding for data in response.data]
            except (RateLimitError, APITimeoutError) as e:
                wait_time = base_wait_time * (2**attempt)
                self.logger.warning(
                    f"Batch embedding generation failed (attempt {attempt + 1}/{retry_count}): {e}"
                )

                if attempt < retry_count - 1:
                    time.sleep(wait_time)
                else:
                    error_msg = f"Failed to generate batch embeddings after {retry_count} attempts"
                    self.logger.error(error_msg)
                    return [None] * len(texts)
            except AuthenticationError as e:
                self.logger.error(f"Authentication or request error (not retrying): {e}")
                return [None] * len(texts)
            except APIError as e:
                wait_time = base_wait_time * (2**attempt)
                self.logger.warning(f"API error (attempt {attempt + 1}/{retry_count}): {e}")

                if attempt < retry_count - 1:
                    time.sleep(wait_time)
                else:
                    error_msg = f"Failed to generate batch embeddings after {retry_count} attempts"
                    self.logger.error(error_msg)
                    return [None] * len(texts)
            except Exception as e:
                self.logger.error(f"Unexpected error generating batch embeddings: {e}")
                return [None] * len(texts)

        return [None] * len(texts)

    def get_embedding_stats(self, embeddings: List[Optional[List[float]]]) -> Dict[str, int]:
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
