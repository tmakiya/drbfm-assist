"""Exception definitions for Gemini client."""

import google.api_core.exceptions
from google import genai

# Retriable exceptions for both generation and embeddings
RETRIABLE_EXCEPTIONS = (
    google.api_core.exceptions.ServiceUnavailable,
    google.api_core.exceptions.TooManyRequests,
    google.api_core.exceptions.DeadlineExceeded,
    google.api_core.exceptions.InternalServerError,
    google.api_core.exceptions.ResourceExhausted,
    google.api_core.exceptions.Aborted,
    ConnectionError,
    genai.errors.ClientError,
)
