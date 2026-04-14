"""DrawerAI Technology Review Agent.

This module defines the main LangGraph workflow for DrawerAI technology analysis.
"""

import logging
import os

from .graph import Context, WorkflowState, graph

__all__ = ["graph", "WorkflowState", "Context"]

# Configure logging level from environment variable
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
