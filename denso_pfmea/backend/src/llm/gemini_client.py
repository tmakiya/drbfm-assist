"""Gemini API client using LangChain ChatGoogleGenerativeAI."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI


def create_gemini_client(
    model_name: str = "gemini-2.5-flash",
    temperature: float = 0.0,
) -> ChatGoogleGenerativeAI:
    """Create a ChatGoogleGenerativeAI client for Vertex AI.

    Args:
        model_name: Gemini model name to use.
        temperature: Generation temperature.
        location: GCP location (unused, kept for API compatibility).

    Returns:
        ChatGoogleGenerativeAI instance configured for Vertex AI.
    """
    return ChatGoogleGenerativeAI(
        model=model_name,
        vertexai=True,
        temperature=temperature,
    )


# Type alias for backward compatibility
GeminiClient = BaseChatModel


__all__ = [
    "GeminiClient",
    "create_gemini_client",
]
