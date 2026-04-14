"""Image analysis utilities using Gemini."""

from pathlib import Path
from typing import Optional

from google.genai.types import Part

from .client import GeminiClient


def analyze_images_with_structured_output(
    image_paths: list[Path],
    system_instruction: str,
    response_schema: dict,
    model_name: str,
    client: Optional[GeminiClient] = None,
) -> dict:
    """Analyze images with structured output using Gemini.

    Args:
        image_paths: List of image file paths
        system_instruction: System instruction for analysis
        response_schema: JSON schema for response
        model_name: Gemini model name
        client: Optional existing GeminiClient instance

    Returns:
        Structured analysis result

    Raises:
        Exception: If analysis fails

    """
    if client is None:
        client = GeminiClient(model_name=model_name)

    contents = [Part.from_text(text="Input:")]
    for path in image_paths:
        mime_type = _get_image_mime_type(path)
        contents.append(Part.from_bytes(data=path.read_bytes(), mime_type=mime_type))

    return client.generate_structured_content(
        contents=contents,
        response_schema=response_schema,
        system_instruction=system_instruction,
    )


def _get_image_mime_type(path: Path) -> str:
    """Get MIME type for image file.

    Args:
        path: Image file path

    Returns:
        MIME type string

    """
    suffix = path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(suffix, "image/jpeg")  # Default to jpeg
