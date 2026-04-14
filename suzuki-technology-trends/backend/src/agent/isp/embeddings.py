"""Embedding generator for ISP vector search."""

from __future__ import annotations

import logging
import math
import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings

logger = logging.getLogger(__name__)


def _normalize_vector(vector: list[float]) -> list[float]:
    """Normalize vector to unit length for dot_product similarity.

    Elasticsearch's dot_product similarity requires unit-length vectors.
    """
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        return [x / norm for x in vector]
    return vector


OUTPUT_DIMENSIONS = 768


class ISPEmbeddingGenerator:
    """Embedding generator for ISP kNN search.

    Uses Google Generative AI gemini-embedding-001 to generate 768-dimensional embeddings
    that are compatible with ISP's embedding field.

    Usage:
        generator = ISPEmbeddingGenerator()
        vector = await generator.generate("search query text")
    """

    def __init__(self, model_name: str = "gemini-embedding-001"):
        """Initialize embedding generator.

        Args:
            model_name: Google AI embedding model name
        """
        self.model_name = model_name
        self._embeddings: GoogleGenerativeAIEmbeddings | None = None

    @property
    def embeddings(self) -> GoogleGenerativeAIEmbeddings:
        """Lazy initialization of embeddings client."""
        if self._embeddings is None:
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model=self.model_name,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                vertexai=True,
                output_dimensionality=OUTPUT_DIMENSIONS,
            )
            logger.debug("Initialized GoogleGenerativeAIEmbeddings")
        return self._embeddings

    async def generate(self, text: str) -> list[float]:
        """Generate embedding vector from text.

        Args:
            text: Text to embed

        Returns:
            768-dimensional normalized embedding vector
        """
        logger.debug("Generating embedding")
        vector = await self.embeddings.aembed_query(
            text, output_dimensionality=OUTPUT_DIMENSIONS
        )
        normalized = _normalize_vector(vector)
        logger.debug("Generated embedding")
        return normalized

    def generate_sync(self, text: str) -> list[float]:
        """Generate embedding vector synchronously.

        Args:
            text: Text to embed

        Returns:
            768-dimensional normalized embedding vector
        """
        logger.debug("Generating embedding (sync)")
        vector = self.embeddings.embed_query(
            text, output_dimensionality=OUTPUT_DIMENSIONS
        )
        normalized = _normalize_vector(vector)
        logger.debug("Generated embedding")
        return normalized
