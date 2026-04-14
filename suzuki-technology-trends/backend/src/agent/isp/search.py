"""Search query builder and result handler for ISP."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ISPDocument:
    """Single ISP document from search results."""

    doc_id: int
    drawing_id: str
    project: str
    ocr_text_snippet: str
    technology_theme: list[str]
    issue_theme: list[str]
    components_theme: list[str]
    score: float = 0.0
    chunk_id: int | None = None
    total_chunks: int | None = None

    @classmethod
    def from_hit(cls, hit: dict[str, Any]) -> ISPDocument:
        """Create from ISP search hit.

        Args:
            hit: Single hit from ISP search response

        Returns:
            ISPDocument instance
        """
        source = hit.get("_source", {})

        # Handle fields that may be string or list
        def ensure_list(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return [value] if value else []

        return cls(
            doc_id=source.get("doc_id", 0),
            drawing_id=source.get("drawing_id", ""),
            project=source.get("project", ""),
            ocr_text_snippet=source.get("ocr_text_snippet", ""),
            technology_theme=ensure_list(source.get("technology_theme")),
            issue_theme=ensure_list(source.get("issue_theme")),
            components_theme=ensure_list(source.get("components_theme")),
            score=hit.get("_score") or 0.0,
            chunk_id=source.get("chunk_id"),
            total_chunks=source.get("total_chunks"),
        )

    def to_reference(self) -> dict[str, Any]:
        """Convert to reference dict for final report.

        Returns:
            Reference dictionary with document metadata
        """
        return {
            "source": self.drawing_id,
            "drawing_id": self.drawing_id,
            "project": self.project,
            "technology": ", ".join(self.technology_theme)
            if self.technology_theme
            else "",
            "issue": ", ".join(self.issue_theme) if self.issue_theme else "",
            "component": ", ".join(self.components_theme)
            if self.components_theme
            else "",
            "snippet": self.ocr_text_snippet[:300] if self.ocr_text_snippet else "",
            "score": self.score,
            "chunk_id": self.chunk_id,
            "total_chunks": self.total_chunks,
        }


@dataclass
class SearchResult:
    """ISP search result container."""

    documents: list[ISPDocument] = field(default_factory=list)
    total_hits: int = 0
    max_score: float = 0.0

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> SearchResult:
        """Create from ISP search response.

        Note: ISP returns hits.total as integer, not object like Elasticsearch.

        Args:
            response: Full ISP search response

        Returns:
            SearchResult instance
        """
        hits = response.get("hits", {})
        hits_list = hits.get("hits", [])

        # ISP returns total as integer (not object like ES)
        total = hits.get("total", 0)
        if isinstance(total, dict):
            total = total.get("value", 0)

        documents = [ISPDocument.from_hit(hit) for hit in hits_list]

        return cls(
            documents=documents,
            total_hits=total,
            max_score=hits.get("max_score") or 0.0,
        )

    def to_rag_context(self, max_docs: int = 10) -> str:
        """Convert to RAG context string for LLM.

        Args:
            max_docs: Maximum number of documents to include

        Returns:
            Formatted string for LLM consumption
        """
        if not self.documents:
            return "【検索結果】\n関連文書は見つかりませんでした。"

        lines = [f"【検索結果】{self.total_hits}件の関連文書が見つかりました。\n"]

        for i, doc in enumerate(self.documents[:max_docs], 1):
            lines.append(f"--- 文書 {i} ---")
            lines.append(f"図面番号: {doc.drawing_id}")
            if doc.chunk_id is not None and doc.total_chunks is not None:
                lines.append(f"チャンク: {doc.chunk_id + 1}/{doc.total_chunks}")
            lines.append(f"プロジェクト: {doc.project}")
            if doc.technology_theme:
                lines.append(f"技術テーマ: {', '.join(doc.technology_theme)}")
            if doc.issue_theme:
                lines.append(f"課題テーマ: {', '.join(doc.issue_theme)}")
            if doc.components_theme:
                lines.append(f"構成品テーマ: {', '.join(doc.components_theme)}")

            # Truncate long content
            content = doc.ocr_text_snippet
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"内容: {content}")
            lines.append("")

        return "\n".join(lines)

    def get_references(self) -> list[dict[str, Any]]:
        """Get reference list for final report.

        Returns:
            List of reference dictionaries
        """
        return [doc.to_reference() for doc in self.documents]

    def get_references_with_dedup(self) -> list[dict[str, Any]]:
        """Get deduplicated reference list for final report.

        Deduplicates by drawing_id, keeping the highest-scoring document.
        Multiple chunks from the same drawing are consolidated into a single entry.

        Returns:
            Deduplicated list of reference dictionaries
        """
        seen: dict[str, dict[str, Any]] = {}
        for doc in self.documents:
            key = doc.drawing_id
            if key not in seen or doc.score > seen[key].get("score", 0):
                seen[key] = doc.to_reference()
        return list(seen.values())


def build_search_query(
    query_vector: list[float],
    interest_keywords: list[str] | None = None,
    tech_keywords: list[str] | None = None,
    component_keywords: list[str] | None = None,
    project_keywords: list[str] | None = None,
    size: int = 20,
) -> dict[str, Any]:
    """Build ISP kNN search query with pre-filtering.

    Query strategy:
    - kNN search on embedding field for semantic similarity
    - Pre-filtering using filter clause for metadata conditions

    Field mapping:
    - interest_keywords -> issue_theme
    - tech_keywords -> technology_theme
    - component_keywords -> components_theme
    - project_keywords -> project

    Args:
        query_vector: Embedding vector (768 dimensions)
        interest_keywords: Issue theme keywords for filtering
        tech_keywords: Technology theme keywords for filtering
        component_keywords: Component theme keywords for filtering
        project_keywords: Project name keywords for filtering
        size: Maximum number of results

    Returns:
        ISP kNN search query dict
    """
    # Build filter conditions for pre-filtering
    must_clauses: list[dict[str, Any]] = []

    if interest_keywords:
        must_clauses.append({"terms": {"issue_theme": interest_keywords}})

    if tech_keywords:
        must_clauses.append({"terms": {"technology_theme": tech_keywords}})

    if component_keywords:
        must_clauses.append({"terms": {"components_theme": component_keywords}})

    if project_keywords:
        must_clauses.append({"terms": {"project": project_keywords}})

    # Build kNN query with pre-filtering
    knn_query: dict[str, Any] = {
        "field": "embedding",
        "query_vector": query_vector,
        "k": size,
        "num_candidates": size * 10,
    }

    # Add filter if conditions exist
    # ISP requires filter to be an array, not an object
    if must_clauses:
        knn_query["filter"] = must_clauses

    logger.debug(f"Built ISP kNN query with {len(must_clauses)} filter conditions")

    return {
        "knn": knn_query,
        "size": size,
        "_source": [
            "doc_id",
            "drawing_id",
            "project",
            "ocr_text_snippet",
            "technology_theme",
            "issue_theme",
            "components_theme",
            "chunk_id",
            "total_chunks",
        ],
    }
