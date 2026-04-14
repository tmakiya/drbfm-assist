"""Embedding generation utilities"""

from .azure_client import AzureOpenAIEmbedder
from .vertexai_client import VertexAIEmbedder

__all__ = ["AzureOpenAIEmbedder", "VertexAIEmbedder"]
