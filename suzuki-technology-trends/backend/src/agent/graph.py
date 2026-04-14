"""DrawerAI Technology Review Workflow.

LangGraph-based workflow for AI-powered technology analysis and review.
This module defines the main graph for the DrawerAI system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from operator import add
from typing import Annotated, Any, Dict, List, Optional

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy
from pydantic import BaseModel, Field

from .defaults import (
    DEFAULT_EXPERT_SELECTION_PROMPT,
    DEFAULT_EXPERTS,
    DEFAULT_REPORT_DESIGNER_PROMPT,
    DEFAULT_REPORT_EXECUTIVE_PROMPT,
    DEFAULT_TURN1_PROMPT,
    DEFAULT_TURN2_PROMPT,
)
from .isp.client import ISPSearchError
from .nodes import (
    generate_report,
    search_rag,
    select_expert_team,
    turn1_analysis,
    turn2_analysis,
)

# =============================================================================
# Configuration Context (Pydantic BaseModel)
# =============================================================================


class Context(BaseModel):
    """Runtime configuration for DrawerAI.

    LangGraph StudioでContextフィールドを表示・編集可能。
    全フィールドにデフォルト値があるため、値を確認した上で編集できる。
    """

    # ===== Tenant =====
    tenant_id: str = Field(default="default", description="テナントID")

    # ===== LLM =====
    model_name: str = Field(default="gemini-2.5-flash", description="使用するLLMモデル")

    # ===== Expert Selection =====
    num_experts: int = Field(default=3, description="選定する専門家の人数")
    experts_json: str = Field(
        default=DEFAULT_EXPERTS,
        description="専門家リスト（JSON文字列）",
    )

    # ===== Prompts (デフォルト値付き) =====
    expert_selection_prompt: str = Field(
        default=DEFAULT_EXPERT_SELECTION_PROMPT,
        description="専門家選定プロンプト",
    )
    turn1_prompt: str = Field(
        default=DEFAULT_TURN1_PROMPT,
        description="ターン1分析プロンプト",
    )
    turn2_prompt: str = Field(
        default=DEFAULT_TURN2_PROMPT,
        description="ターン2分析プロンプト",
    )
    report_executive_prompt: str = Field(
        default=DEFAULT_REPORT_EXECUTIVE_PROMPT,
        description="エグゼクティブ向けレポートプロンプト",
    )
    report_designer_prompt: str = Field(
        default=DEFAULT_REPORT_DESIGNER_PROMPT,
        description="デザイナー向けレポートプロンプト",
    )

    # ===== Retry =====
    max_retries: int = Field(default=3, description="最大リトライ回数")
    initial_delay: float = Field(default=10.0, description="初回リトライ待機秒数")

    # ===== Embedding =====
    embedding_model: str = Field(
        default="gemini-embedding-001",
        description="Vertex AI埋め込みモデル名（768次元）",
    )


# =============================================================================
# State Definition
# =============================================================================


@dataclass
class WorkflowState:
    """Workflow state for DrawerAI technology review.

    Simplified state with clear separation of input, internal, and output fields.
    """

    # ===== Input =====
    topic: str = ""
    use_case: str = ""  # "executive" | "designer"
    interest_keywords: List[str] = field(default_factory=list)
    tech_keywords: List[str] = field(default_factory=list)
    component_keywords: List[str] = field(default_factory=list)
    additional_context: str = ""

    # ===== Internal (generated within workflow) =====
    rag_context: str = ""  # RAG search results
    expert_team: List[Dict[str, str]] = field(default_factory=list)
    analyses: List[Dict[str, Any]] = field(default_factory=list)

    # ===== Output =====
    # messages: Streaming support with Annotated[List, add]
    messages: Annotated[List[Dict[str, Any]], add] = field(default_factory=list)
    final_report: str = ""
    references: List[Dict[str, Any]] = field(default_factory=list)

    # ===== Error =====
    # Kept in State because Run API has no error field
    error: Optional[str] = None


# =============================================================================
# Build Graph
# =============================================================================


def build_graph() -> CompiledStateGraph:
    """Build and compile the DrawerAI workflow graph.

    Node structure:
    [START]
        ↓
    select_expert_team    # Expert team selection
        ↓
    turn1_analysis        # Turn 1: Perspective identification
        ↓
    search_rag            # RAG search (new)
        ↓
    turn2_analysis        # Turn 2: Detailed analysis
        ↓
    generate_report       # Final report generation
        ↓
    [END]
    """
    workflow = StateGraph(WorkflowState, context_schema=Context)

    # Add nodes
    workflow.add_node("select_expert_team", select_expert_team)
    workflow.add_node("turn1_analysis", turn1_analysis)
    workflow.add_node(
        "search_rag",
        search_rag,
        retry=RetryPolicy(
            initial_interval=1.0,
            max_attempts=3,
            backoff_factor=2.0,
            retry_on=(ISPSearchError, ConnectionError, TimeoutError),
        ),
    )
    workflow.add_node("turn2_analysis", turn2_analysis)
    workflow.add_node("generate_report", generate_report)

    # Add edges (sequential workflow)
    workflow.set_entry_point("select_expert_team")
    workflow.add_edge("select_expert_team", "turn1_analysis")
    workflow.add_edge("turn1_analysis", "search_rag")
    workflow.add_edge("search_rag", "turn2_analysis")
    workflow.add_edge("turn2_analysis", "generate_report")
    workflow.add_edge("generate_report", END)

    return workflow.compile(name="DrawerAI Technology Review")


# Export the compiled graph
graph = build_graph()
