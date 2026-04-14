"""ISP query building utilities and result processing

This module provides query builders for ISP that are compatible with Elasticsearch DSL.
ISP uses Japanese text analysis with the .japanese suffix for full-text search fields.
"""

from typing import Any, Dict, List, Literal, Optional

import structlog

logger = structlog.stdlib.get_logger(__name__)


def build_field_filters(
    field_filters: Dict[str, Any],
    model_numbers: Optional[List[str]] = None,
    model_field: str = "model_number",
) -> List[Dict[str, Any]]:
    """Build generic ISP filters for any field with optional model number filtering

    Args:
        field_filters: Dictionary of field names to values for term/terms filtering
        model_numbers: Optional list of model numbers for wildcard filtering
        model_field: Field name for model number filtering (default: "model_number")

    Returns:
        List of ISP filter clauses

    """
    isp_filters = []

    # Add term/terms filters for each field
    for field_name, field_value in field_filters.items():
        if isinstance(field_value, list):
            # Use terms query for list values (OR condition)
            isp_filters.append({"terms": {field_name: field_value}})
        else:
            # Use term query for single value
            isp_filters.append({"term": {field_name: field_value}})

    # Add model number prefix filters if provided
    # Note: ISP uses prefix matching instead of wildcard (deprecated)
    # The field must have "prefix" matching enabled in the index mapping
    if model_numbers:
        model_queries = []
        for model in model_numbers:
            # Use match_phrase with .prefix subfield for prefix matching
            model_queries.append({"match_phrase": {f"{model_field}.prefix": model}})

        if model_queries:
            # Combine multiple model queries with should (OR)
            model_filter = {"bool": {"should": model_queries, "minimum_should_match": 1}}
            isp_filters.append(model_filter)
            logger.info("Applied model number filters", model_numbers=model_numbers)

    return isp_filters


def build_field_keyword_query(
    keywords: List[str],
    search_field: str,
    match_type: Literal["match", "match_phrase"] = "match",
    filters: Optional[List[Dict[str, Any]]] = None,
    minimum_should_match: int = 1,
    use_japanese_analyzer: bool = True,
) -> Dict[str, Any]:
    """Build keyword search query for a specific field with optional filters

    Args:
        keywords: List of keywords to search for
        search_field: Field to search in (without .japanese suffix)
        match_type: Type of match query ("match" or "match_phrase")
                   Note: ISP only supports "match_phrase", "match" will be converted
        filters: Optional pre-built filter clauses
        minimum_should_match: Minimum number of keywords that should match
        use_japanese_analyzer: Whether to use .japanese suffix for the field

    Returns:
        ISP query DSL

    """
    # Add .japanese suffix for full-text search if needed
    actual_field = f"{search_field}.japanese" if use_japanese_analyzer else search_field

    # ISP only supports match_phrase, not match
    # Convert "match" to "match_phrase" for ISP compatibility
    isp_match_type = "match_phrase"

    # Build should queries for keywords
    should_queries = []
    for keyword in keywords:
        should_queries.append({isp_match_type: {actual_field: keyword}})

    # Build bool query
    bool_query: Dict[str, Any] = {
        "bool": {
            "should": should_queries,
            "minimum_should_match": minimum_should_match,
        }
    }

    # Add filters if provided
    if filters:
        bool_query["bool"]["filter"] = filters

    query = {
        "query": bool_query,
    }

    logger.debug("Built keyword query", field=actual_field, keyword_count=len(keywords))

    return query


def build_knn_query_with_custom_filters(
    query_embedding: List[float],
    size: int = 10,
    filters: Optional[List[Dict[str, Any]]] = None,
    field: str = "embedding",
    num_candidates: Optional[int] = None,
) -> Dict[str, Any]:
    """Build KNN query with custom pre-built filters

    Args:
        query_embedding: Query vector for similarity search
        size: Number of results to return
        filters: Optional pre-built filter clauses
        field: Vector field name (default: "embedding")
        num_candidates: Number of candidates for KNN search

    Returns:
        ISP KNN query DSL

    """
    if num_candidates is None:
        num_candidates = max(size * 10, 100)

    # Base KNN query structure
    knn_query: Dict[str, Any] = {
        "field": field,
        "query_vector": query_embedding,
        "k": size,
        "num_candidates": num_candidates,
    }

    # Add filters if provided
    if filters:
        knn_query["filter"] = {"bool": {"filter": filters}}

    query = {
        "knn": knn_query,
    }

    logger.info(
        "Built KNN query",
        k=size,
        num_candidates=num_candidates,
        filter_count=len(filters or []),
    )

    return query
