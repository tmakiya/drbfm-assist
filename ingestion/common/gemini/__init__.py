"""Gemini client module for image analysis and embeddings."""

from .client import GeminiClient
from .embeddings import generate_embeddings_batch
from .exceptions import RETRIABLE_EXCEPTIONS
from .image_analysis import analyze_images_with_structured_output

__all__ = [
    "GeminiClient",
    "analyze_images_with_structured_output",
    "generate_embeddings_batch",
    "RETRIABLE_EXCEPTIONS",
]
