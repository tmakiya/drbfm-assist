"""Sanitization utilities for user inputs.

This module provides functions for sanitizing user inputs to prevent
prompt injection attacks and ensure safe handling of data.
"""

from __future__ import annotations

import re
from typing import List


# Input length limits
ADDITIONAL_CONTEXT_MAX_LENGTH = 10000
TOPIC_MAX_LENGTH = 500
KEYWORD_MAX_LENGTH = 100
KEYWORDS_MAX_COUNT = 50


def sanitize_for_prompt(text: str) -> str:
    """Sanitize text for safe use in LLM prompts.

    Removes or neutralizes patterns that could be used for prompt injection.

    Args:
        text: The text to sanitize

    Returns:
        Sanitized text safe for LLM consumption
    """
    if not text:
        return ""

    sanitized = text

    # Remove system instruction patterns (case-insensitive)
    system_patterns = [
        r"\[SYSTEM\]",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<SYS>>",
        r"<</SYS>>",
        r"```system",
        r"```assistant",
        r"```user",
    ]

    for pattern in system_patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

    return sanitized.strip()


def sanitize_keywords(keywords: List[str]) -> List[str]:
    """Sanitize a list of keywords.

    Args:
        keywords: List of keyword strings

    Returns:
        Sanitized list of keywords
    """
    if not keywords:
        return []

    sanitized = []
    for keyword in keywords[:KEYWORDS_MAX_COUNT]:
        if isinstance(keyword, str) and keyword.strip():
            clean = sanitize_for_prompt(keyword.strip())
            if clean and len(clean) <= KEYWORD_MAX_LENGTH:
                sanitized.append(clean)

    return sanitized


def truncate_string(text: str, max_length: int) -> str:
    """Truncate a string to a maximum length.

    Args:
        text: The text to truncate
        max_length: Maximum allowed length

    Returns:
        Truncated text
    """
    if not text:
        return ""
    return text[:max_length] if len(text) > max_length else text


def sanitize_topic(topic: str) -> str:
    """Sanitize and truncate a topic string.

    Args:
        topic: The topic string

    Returns:
        Sanitized and truncated topic
    """
    if not topic:
        return ""

    sanitized = sanitize_for_prompt(topic)
    return truncate_string(sanitized, TOPIC_MAX_LENGTH)


def sanitize_markdown_output(content: str) -> str:
    """Sanitize LLM-generated Markdown output.

    Detects and repairs repetitive patterns and broken table structures
    that occur when the model falls into a generation loop.

    Args:
        content: Raw Markdown content from LLM

    Returns:
        Sanitized Markdown with repaired table structures
    """
    if not content:
        return ""

    # Fix runs of 20+ identical characters (e.g. "------...------")
    content = re.sub(r"(-){20,}", "------", content)
    content = re.sub(r"(\|){5,}", "|", content)
    content = re.sub(r"( ){50,}", " ", content)

    # Normalize table separator rows that grew too wide
    content = re.sub(r"\|[-\s]{50,}\|", "|------|", content)

    # Truncate abnormally long table cells (over 300 chars between pipes)
    def _truncate_cell(match: re.Match) -> str:
        cell = match.group(1).strip()
        if len(cell) > 300:
            return f"| {cell[:200]}… |"
        return match.group(0)

    content = re.sub(r"\|([^|\n]{300,})\|", _truncate_cell, content)

    return content


def sanitize_additional_context(context: str) -> str:
    """Sanitize and truncate additional context.

    Args:
        context: The additional context string

    Returns:
        Sanitized and truncated context
    """
    if not context:
        return ""

    sanitized = sanitize_for_prompt(context)
    return truncate_string(sanitized, ADDITIONAL_CONTEXT_MAX_LENGTH)
