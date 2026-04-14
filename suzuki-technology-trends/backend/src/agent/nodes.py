"""Graph nodes for DrawerAI Technology Review.

This module contains all node functions for the LangGraph workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from .defaults import DEFAULT_EXPERTS_LIST
from .sanitize import (
    sanitize_additional_context,
    sanitize_for_prompt,
    sanitize_keywords,
    sanitize_markdown_output,
    sanitize_topic,
)
from .utils import format_references, format_references_for_prompt, get_llm

if TYPE_CHECKING:
    from langgraph.types import Runtime

    from .graph import Context, WorkflowState

logger = logging.getLogger(__name__)


def build_additional_context_section(additional_context: str) -> str:
    """Build the additional context section for prompts.

    Args:
        additional_context: Raw additional context from user input

    Returns:
        Formatted section string, or empty string if context is empty
    """
    if not additional_context or not additional_context.strip():
        return ""

    sanitized = sanitize_additional_context(additional_context)
    if not sanitized:
        return ""

    return f"\n【追加コンテキスト】\n{sanitized}\n"


def build_theme_section(
    interest_keywords: List[str],
    tech_keywords: List[str],
    component_keywords: List[str],
) -> str:
    """Build the theme section for reports showing only user-provided keywords.

    Args:
        interest_keywords: User-provided interest/issue keywords
        tech_keywords: User-provided technology keywords
        component_keywords: User-provided component keywords

    Returns:
        Formatted markdown table with only non-empty keyword categories,
        or a message indicating no user input if all are empty
    """
    rows = []
    if interest_keywords:
        rows.append(f"| 対象課題 | {', '.join(interest_keywords)} |")
    if tech_keywords:
        rows.append(f"| 技術テーマ | {', '.join(tech_keywords)} |")
    if component_keywords:
        rows.append(f"| 構成品テーマ | {', '.join(component_keywords)} |")

    if not rows:
        return ""

    header = "| 分類 | 内容 |\n|------|------|"
    return header + "\n" + "\n".join(rows)


def create_chain(model_name: str, prompt_template: str, max_retries: int) -> Any:
    """Create a reusable chain with model, prompt, and output parser.

    Args:
        model_name: Name of the LLM model
        prompt_template: Template string for the prompt
        max_retries: Maximum number of retry attempts

    Returns:
        Configured chain ready for invocation
    """
    model = get_llm(model_name).with_retry(
        stop_after_attempt=max_retries,
        wait_exponential_jitter=True,
    )
    prompt = ChatPromptTemplate.from_template(prompt_template)
    return prompt | model | StrOutputParser()


def parse_expert_selection(
    response: str, experts: List[Dict], num_experts: int
) -> List[str]:
    """Parse expert selection from LLM response.

    Args:
        response: LLM response containing selected expert names
        experts: List of available experts
        num_experts: Target number of experts to select

    Returns:
        List of selected expert names
    """
    # Try to parse JSON array first
    json_match = re.search(r"\[.*?\]", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Fallback: find expert names in response text
    return [e["name"] for e in experts[:num_experts] if e["name"] in response]


def ensure_team_size(
    selected_names: List[str],
    experts: List[Dict],
    min_size: int = 2,
    max_size: int = None,
) -> List[Dict]:
    """Ensure the selected team meets size requirements.

    Args:
        selected_names: Names of selected experts
        experts: List of all available experts
        min_size: Minimum team size (default: 2)
        max_size: Maximum team size (default: None)

    Returns:
        List of selected expert dictionaries with proper size
    """
    # Build initial team from selected names
    selected_team = [
        {"name": e["name"], "persona": e["persona"]}
        for e in experts
        if e["name"] in selected_names
    ]

    # Add experts if team is too small
    if len(selected_team) < min_size:
        remaining = [e for e in experts if e["name"] not in selected_names]
        while len(selected_team) < min_size and remaining:
            expert = remaining.pop(0)
            selected_team.append({"name": expert["name"], "persona": expert["persona"]})

    # Trim if team is too large
    if max_size and len(selected_team) > max_size:
        selected_team = selected_team[:max_size]

    return selected_team


async def parallel_process_experts(
    items: List[Dict],
    processor: Callable,
    *processor_args,
) -> Tuple[List[Dict], List[Dict]]:
    """Process multiple experts in parallel and maintain order.

    Args:
        items: List of items to process
        processor: Async function to process each item
        processor_args: Additional arguments to pass to processor

    Returns:
        Tuple of (processed_items, messages) both in original order
    """
    # Execute all processors in parallel
    results = await asyncio.gather(
        *[processor(idx, item, *processor_args) for idx, item in enumerate(items)]
    )

    # Sort by index to preserve original order
    results_sorted = sorted(results, key=lambda x: x[0])

    # Separate items and messages
    processed_items = [r[1] for r in results_sorted]
    messages = [r[2] for r in results_sorted]

    return processed_items, messages


def create_error_response(
    name: str,
    persona: str,
    error: Exception,
    turn: int,
    include_turn1: str = None,
) -> Tuple[Dict, Dict]:
    """Create standardized error response for failed expert processing.

    Args:
        name: Expert name
        persona: Expert persona
        error: The exception that occurred
        turn: Turn number (1 or 2)
        include_turn1: Turn 1 response to include (for turn 2 errors)

    Returns:
        Tuple of (analysis_dict, message_dict)
    """
    error_msg = f"Error ({name}): {str(error)[:200]}"

    analysis = {
        "name": name,
        "persona": persona,
        "turn1_response": include_turn1
        if include_turn1
        else error_msg
        if turn == 1
        else "",
        "turn2_response": error_msg if turn == 2 else "",
        "references": [],
    }

    message = {
        "role": "ai",
        "content": error_msg,
        "agent_type": name,
        "turn": turn,
    }

    return analysis, message


async def select_expert_team(
    state: WorkflowState,
    *,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Select expert team based on context.

    Args:
        state: Current workflow state
        runtime: LangGraph runtime with context

    Returns:
        State update with selected expert team
    """
    logger.debug("=== LangGraph: Expert Team Selection Node Started ===")

    ctx = runtime.context

    # Sanitize user inputs (defense in depth)
    topic = sanitize_topic(state.topic)
    tech_keywords = sanitize_keywords(state.tech_keywords or [])
    interest_keywords = sanitize_keywords(state.interest_keywords or [])

    # Get configuration from context
    model_name = ctx.model_name
    num_experts = ctx.num_experts
    experts_json = ctx.experts_json
    prompt_template = ctx.expert_selection_prompt
    max_retries = ctx.max_retries

    # Parse experts from JSON
    try:
        experts = json.loads(experts_json)
    except json.JSONDecodeError:
        logger.warning("Failed to parse experts_json, using defaults")
        experts = DEFAULT_EXPERTS_LIST

    # Create expert descriptions for prompt
    experts_desc = "\n".join(
        [
            f"{i + 1}. {e['name']}: {e['persona'][:200]}..."
            for i, e in enumerate(experts)
        ]
    )

    # Build additional context section
    additional_context_section = build_additional_context_section(
        state.additional_context
    )

    # Create and execute chain
    chain = create_chain(model_name, prompt_template, max_retries)

    try:
        response = await chain.ainvoke(
            {
                "topic": topic,
                "tech": ", ".join(tech_keywords) if tech_keywords else "なし",
                "issue": ", ".join(interest_keywords) if interest_keywords else "なし",
                "experts_desc": experts_desc,
                "additional_context_section": additional_context_section,
            }
        )

        # Parse selection and ensure proper team size
        selected_names = parse_expert_selection(response, experts, num_experts)
        selected_team = ensure_team_size(
            selected_names, experts, min_size=2, max_size=num_experts
        )

        logger.debug(f"Expert team selected: {[e['name'] for e in selected_team]}")
        return {"expert_team": selected_team}

    except Exception as e:
        logger.error(f"Expert selection error: {e}")
        # Fallback to first N experts
        selected_team = [
            {"name": e["name"], "persona": e["persona"]} for e in experts[:num_experts]
        ]
        return {"expert_team": selected_team}


async def turn1_analysis(
    state: WorkflowState,
    *,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Turn 1: Each expert identifies analysis perspectives.

    Args:
        state: Current workflow state
        runtime: LangGraph runtime with context

    Returns:
        State update with expert analyses and messages
    """
    logger.debug("=== LangGraph: Turn 1 Analysis Node Started ===")

    ctx = runtime.context
    expert_team = state.expert_team

    # Sanitize user input (defense in depth)
    topic = sanitize_topic(state.topic)

    # Get configuration from context
    model_name = ctx.model_name
    prompt_template = ctx.turn1_prompt
    max_retries = ctx.max_retries

    # Build additional context section
    additional_context_section = build_additional_context_section(
        state.additional_context
    )

    # Create shared chain for all experts
    chain = create_chain(model_name, prompt_template, max_retries)

    async def process_expert(
        idx: int, expert: Dict, chain: Any, topic: str, additional_context_section: str
    ) -> Tuple[int, Dict, Dict]:
        """Process a single expert's Turn 1 analysis."""
        name = expert.get("name", f"Expert{idx + 1}")
        persona = expert.get("persona", "General AI assistant")

        try:
            response = await chain.ainvoke(
                {
                    "name": name,
                    "persona": persona,
                    "topic": topic,
                    "additional_context_section": additional_context_section,
                }
            )

            analysis = {
                "name": name,
                "persona": persona,
                "turn1_response": response,
                "turn2_response": "",
                "references": [],
            }

            message = {
                "role": "ai",
                "content": response,
                "agent_type": name,
                "turn": 1,
            }

            return idx, analysis, message

        except Exception as e:
            logger.error(f"Turn 1 error ({name}): {e}")
            analysis, message = create_error_response(name, persona, e, turn=1)
            return idx, analysis, message

    # Process all experts in parallel
    analyses, messages = await parallel_process_experts(
        expert_team, process_expert, chain, topic, additional_context_section
    )

    return {
        "analyses": analyses,
        "messages": messages,
    }


async def search_rag(
    state: WorkflowState,
    config: RunnableConfig,
    *,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Search RAG for relevant information using ISP kNN search.

    This node performs ISP (Interactive Search Platform) kNN search with
    pre-filtering to gather relevant context for Turn 2 analysis.

    Args:
        state: Current workflow state
        config: LangGraph config containing auth user info
        runtime: LangGraph runtime with context

    Returns:
        State update with rag_context and references
    """
    logger.debug("=== LangGraph: RAG Search Node Started ===")

    ctx = runtime.context
    topic = state.topic
    tech_keywords = state.tech_keywords
    interest_keywords = state.interest_keywords
    component_keywords = state.component_keywords

    # Get tenant_id and internal_token from config (extracted from JWT by auth.py)
    from .auth import get_internal_token_from_config, get_tenant_id_from_config

    tenant_id = get_tenant_id_from_config(config)
    internal_token = get_internal_token_from_config(config)

    if not tenant_id:
        logger.error("tenant_id not found in config")
        return {
            "rag_context": "【検索エラー】tenant_idが取得できませんでした。",
            "references": [],
        }

    try:
        # Import ISP client and embeddings (lazy import to avoid circular deps)
        from .isp import (
            SearchResult,
            build_search_query,
            create_isp_client,
            get_index_alias,
        )
        from .isp.embeddings import ISPEmbeddingGenerator

        # Generate embedding vector for the topic
        logger.debug("Generating embedding for topic")
        generator = ISPEmbeddingGenerator(model_name=ctx.embedding_model)
        query_vector = await generator.generate(topic)
        logger.debug(f"Generated embedding with {len(query_vector)} dimensions")

        # Build kNN search query with pre-filtering
        query = build_search_query(
            query_vector=query_vector,
            interest_keywords=interest_keywords,
            tech_keywords=tech_keywords,
            component_keywords=component_keywords,
            size=20,
        )

        logger.debug("ISP kNN search started")

        # Create ISP client with internal token for authentication
        index_alias = get_index_alias(tenant_id=tenant_id)

        async with create_isp_client(
            tenant_id=tenant_id,
            internal_token=internal_token,
        ) as client:
            response = await client.search(index_alias, query)
            result = SearchResult.from_response(response)

            logger.debug(f"ISP kNN search completed: {result.total_hits} hits")

            # Format for LLM consumption
            rag_context = result.to_rag_context()
            # Use deduplicated references
            references = result.get_references_with_dedup()

            return {
                "rag_context": rag_context,
                "references": references,
            }

    except Exception as e:
        logger.error(f"ISP search error: {e}")

        # Fallback to placeholder on error
        rag_context = f"""【検索クエリ】
トピック: {topic}
技術キーワード: {", ".join(tech_keywords) if tech_keywords else "なし"}
課題キーワード: {", ".join(interest_keywords) if interest_keywords else "なし"}

【検索結果】
ISP検索でエラーが発生しました: {str(e)[:200]}"""

        return {
            "rag_context": rag_context,
            "references": [],
        }


async def turn2_analysis(
    state: WorkflowState,
    *,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Turn 2: Each expert creates detailed report with RAG references.

    Args:
        state: Current workflow state
        runtime: LangGraph runtime with context

    Returns:
        State update with updated analyses and messages
    """
    logger.debug("=== LangGraph: Turn 2 Analysis Node Started ===")

    ctx = runtime.context
    analyses = list(state.analyses)

    # Sanitize user input (defense in depth)
    topic = sanitize_topic(state.topic)
    rag_context = sanitize_for_prompt(state.rag_context or "情報なし")

    # Get configuration from context
    model_name = ctx.model_name
    prompt_template = ctx.turn2_prompt
    max_retries = ctx.max_retries

    # Build additional context section
    additional_context_section = build_additional_context_section(
        state.additional_context
    )

    # Create shared chain for all experts
    chain = create_chain(model_name, prompt_template, max_retries)

    async def process_analysis(
        idx: int,
        analysis: Dict,
        chain: Any,
        topic: str,
        rag_context: str,
        additional_context_section: str,
    ) -> Tuple[int, Dict, Dict]:
        """Process a single expert's Turn 2 analysis."""
        name = analysis.get("name", f"Expert{idx + 1}")
        persona = analysis.get("persona", "")
        turn1_response = analysis.get("turn1_response", "")

        try:
            response = await chain.ainvoke(
                {
                    "name": name,
                    "persona": persona,
                    "topic": topic,
                    "prev_response": turn1_response,
                    "rag_info": rag_context,
                    "additional_context_section": additional_context_section,
                }
            )

            updated_analysis = {
                "name": name,
                "persona": persona,
                "turn1_response": turn1_response,
                "turn2_response": response,
                "references": [],
            }

            message = {
                "role": "ai",
                "content": response,
                "agent_type": name,
                "turn": 2,
            }

            return idx, updated_analysis, message

        except Exception as e:
            logger.error(f"Turn 2 error ({name}): {e}")
            updated_analysis, message = create_error_response(
                name, persona, e, turn=2, include_turn1=turn1_response
            )
            return idx, updated_analysis, message

    # Process all analyses in parallel
    updated_analyses, messages = await parallel_process_experts(
        analyses,
        process_analysis,
        chain,
        topic,
        rag_context,
        additional_context_section,
    )

    return {
        "analyses": updated_analyses,
        "messages": messages,
    }


async def generate_report(
    state: WorkflowState,
    *,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Generate final consolidated report.

    Args:
        state: Current workflow state
        runtime: LangGraph runtime with context

    Returns:
        State update with final_report
    """
    logger.debug("=== LangGraph: Final Report Generation Node Started ===")

    ctx = runtime.context
    messages = state.messages
    references = state.references
    topic = state.topic
    use_case = state.use_case

    # Get configuration from context
    model_name = ctx.model_name
    max_retries = ctx.max_retries

    # Choose prompt based on use case
    if "設計" in use_case or "部品開発" in use_case:
        prompt_template = ctx.report_designer_prompt
    else:
        prompt_template = ctx.report_executive_prompt

    # Build additional context section
    additional_context_section = build_additional_context_section(
        state.additional_context
    )

    # Build theme section (only shows user-provided keywords)
    theme_section = build_theme_section(
        state.interest_keywords,
        state.tech_keywords,
        state.component_keywords,
    )

    # Create chain for report generation
    chain = create_chain(model_name, prompt_template, max_retries)

    # Format discussion history (専門家名・ターン番号を除去し「議論」としてラベル付け)
    full_discussion = "\n\n---\n\n".join(
        [f"**議論:**\n{msg.get('content', '')}" for msg in messages]
    )

    # Format references for prompt (so LLM knows actual drawing_ids)
    references_info = format_references_for_prompt(references)

    try:
        report_content = await chain.ainvoke(
            {
                "topic": topic,
                "interest_keywords": ", ".join(state.interest_keywords),
                "tech_keywords": ", ".join(state.tech_keywords),
                "component_keywords": ", ".join(state.component_keywords),
                "full_discussion": full_discussion,
                "references_info": references_info,
                "additional_context_section": additional_context_section,
                "theme_section": theme_section,
            }
        )

        report_content = sanitize_markdown_output(report_content)

        references_summary = format_references(references)
        final_report = f"{report_content}\n\n---\n\n{references_summary}"

        return {"final_report": final_report}

    except Exception as e:
        logger.error(f"Final report generation error: {e}")
        error_report = f"""# レポート生成エラー

## エラー内容
{str(e)}
"""
        return {
            "final_report": error_report,
            "error": str(e),
        }
