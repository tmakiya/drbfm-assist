"""Simple debug graph to verify tenant_id extraction."""

from typing import Any, Dict, Optional

from drassist.auth import get_tenant_id_from_config
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
import structlog

logger = structlog.stdlib.get_logger(__name__)
from pydantic import BaseModel, Field


class DebugState(BaseModel):
    """State for debug workflow."""

    tenant_id: Optional[str] = Field(None, description="Extracted tenant_id")
    error: Optional[str] = Field(None, description="Error message if any")


def show_tenant_id(state: DebugState, config: RunnableConfig) -> Dict[str, Any]:
    """Show tenant_id from config."""
    tenant_id = get_tenant_id_from_config(config)
    logger.info("Extracted tenant_id", tenant_id=tenant_id)
    return {"tenant_id": tenant_id}


# Create graph
workflow = StateGraph(DebugState)
workflow.add_node("show_tenant_id", show_tenant_id)
workflow.add_edge(START, "show_tenant_id")
workflow.add_edge("show_tenant_id", END)

graph = workflow.compile()
