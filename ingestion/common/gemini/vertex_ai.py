"""Vertex AI initialization utilities."""

import threading
from typing import Optional, Tuple

import vertexai
from google.auth import default
from google.auth.credentials import Credentials
from loguru import logger


class VertexAIInitializer:
    """Thread-safe Vertex AI initializer (singleton pattern)."""

    _instance: Optional["VertexAIInitializer"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._credentials: Optional[Credentials] = None
        self._project_id: Optional[str] = None
        self._initialized_locations: set[str] = set()
        self._init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "VertexAIInitializer":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def initialize(self, location: str) -> Tuple[Credentials, str]:
        """Initialize Vertex AI for given location (idempotent).

        Args:
            location: GCP location (e.g., "us-central1")

        Returns:
            Tuple of (credentials, project_id)

        """
        with self._init_lock:
            if self._credentials is None:
                self._credentials, self._project_id = default()
                logger.info(f"Vertex AI credentials obtained: project={self._project_id}")

            if location not in self._initialized_locations:
                vertexai.init(
                    project=self._project_id,
                    location=location,
                    credentials=self._credentials,
                )
                self._initialized_locations.add(location)
                logger.info(f"Vertex AI initialized: location={location}")

        return self._credentials, self._project_id


def get_vertex_ai_credentials(location: str = "us-central1") -> Tuple[Credentials, str]:
    """Get Vertex AI credentials and project ID.

    Args:
        location: GCP location (e.g., "us-central1")

    Returns:
        Tuple of (credentials, project_id)

    """
    return VertexAIInitializer.get_instance().initialize(location)
