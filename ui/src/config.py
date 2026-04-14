"""Configuration management for DRBFM Workflow Application."""

import sys
from pathlib import Path

from loguru import logger
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    backend_url: str = "http://backend:8123"
    cf_access_client_id: str = ""
    cf_access_client_secret: str = ""
    langsmith_api_key: str = ""
    graph_id: str = "drassist-ebara"
    log_level: str = "INFO"
    drawer_base_url: str = "https://caddi-drawer.com"
    internal_token: str | None = None  # For local development only
    environment: str = "development"  # "development" or "production"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"

    @property
    def allow_token_fallback(self) -> bool:
        """Allow fallback to INTERNAL_TOKEN only in development."""
        return not self.is_production

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        extra = "ignore"


settings = Settings()


def configure_logger() -> None:
    """Configure structured logger for k8s (stdout/stderr)."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stdout,
        format="{message}",
        level=settings.log_level,
        serialize=True,  # Output as JSON for structured logging
    )


# Configure logger on module load
configure_logger()
