"""Utility functions for DrawerAI Technology Review.

This module contains helper functions used by graph nodes.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def get_llm(model_name: str | None = None):
    """Get the LLM model.

    Args:
        model_name: Optional model name override (default: gemini-2.5-flash)

    Returns:
        ChatGoogleGenerativeAI instance

    Note:
        Uses Application Default Credentials (ADC) for authentication.
        - Local: Run `gcloud auth application-default login`
        - Deployed: Automatically uses service account credentials
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = model_name or "gemini-2.5-flash"
    return ChatGoogleGenerativeAI(
        model=model,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        vertexai=True,
        temperature=0.2,
        max_output_tokens=8192,
        top_p=0.95,
    )


def format_references_for_prompt(references: List[Dict[str, Any]]) -> str:
    """Format reference information for LLM prompts.

    Provides drawing_id and project information for the LLM to use
    when generating reports with proper references.

    Args:
        references: List of reference dictionaries from RAG search

    Returns:
        Formatted string for prompt consumption (sanitized)
    """
    from .sanitize import sanitize_for_prompt

    if not references:
        return "【参照した図面情報】\n参照した図面はありません。"

    lines = ["【参照した図面情報】"]
    lines.append("以下の図面を参照しました。レポート内で図面に言及する際は、必ず実際の図面番号を使用してください。\n")

    for ref in references:
        drawing_id = sanitize_for_prompt(ref.get("drawing_id", "") or "")
        project = sanitize_for_prompt(ref.get("project", "") or "")
        technology = sanitize_for_prompt(ref.get("technology", "") or "")
        source = sanitize_for_prompt(ref.get("source", "") or "")

        if drawing_id:
            line_parts = [f"- 図面番号: {drawing_id}"]
            if source:
                line_parts.append(f"ファイル名: {source}")
            if project:
                line_parts.append(f"プロジェクト: {project}")
            if technology:
                line_parts.append(f"技術テーマ: {technology}")
            lines.append(", ".join(line_parts))

    return "\n".join(lines)


def format_references(all_references: List[Dict[str, Any]]) -> str:
    """Format reference information for the final report.

    Groups references by project and includes detailed metadata.

    Args:
        all_references: List of reference dictionaries

    Returns:
        Formatted markdown string
    """
    if not all_references:
        return "## 参照情報源一覧\n\n本分析では外部参照情報はありません。"

    lines = ["## 参照情報源一覧（全専門家が参照したRAGデータ）"]
    lines.append(
        f"\n本分析では、合計 **{len(all_references)}件** のRAG情報源を参照しました。\n"
    )

    # Group by project
    by_project: Dict[str, List[Dict[str, Any]]] = {}
    for ref in all_references:
        proj = ref.get("project", "その他") or "その他"
        if proj not in by_project:
            by_project[proj] = []
        by_project[proj].append(ref)

    if by_project:
        lines.append("\n### プロジェクト別")
        for proj_name, refs in sorted(by_project.items()):
            lines.append(f"\n**{proj_name}** ({len(refs)}件):")
            for ref in refs[:10]:
                drawing_id = ref.get("drawing_id", "不明")
                ref_line = f"- {drawing_id}"
                lines.append(ref_line)

            if len(refs) > 10:
                lines.append(f"  ...他 {len(refs) - 10}件")

    return "\n".join(lines)
