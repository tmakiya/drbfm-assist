"""Elasticsearch query building utilities and result processing"""

from typing import Any, Dict, List, Literal, Optional

from loguru import logger


def build_field_filters(
    field_filters: Dict[str, Any],
    model_numbers: Optional[List[str]] = None,
    exclude_model_numbers: Optional[List[str]] = None,
    model_field: str = "model_number",
) -> List[Dict[str, Any]]:
    """Build generic Elasticsearch filters for any field with optional model number filtering.

    Args:
        field_filters: Dictionary of field names to values for term/terms filtering.
        model_numbers: Optional list of model numbers for wildcard filtering (inclusion).
        exclude_model_numbers: Optional list of model numbers for wildcard filtering (exclusion).
        model_field: Field name for model number filtering (default: "model_number").

    Returns:
        List of Elasticsearch filter clauses.
    """
    es_filters = []

    # Add term/terms filters for each field
    for field_name, field_value in field_filters.items():
        if isinstance(field_value, list):
            # Use terms query for list values (OR condition)
            es_filters.append({"terms": {field_name: field_value}})
        else:
            # Use term query for single value
            es_filters.append({"term": {field_name: field_value}})

    # Add model number wildcard filters if provided
    if model_numbers:
        model_queries = []
        for model in model_numbers:
            # Use wildcard for prefix matching
            model_queries.append({"wildcard": {model_field: f"{model}*"}})

        if model_queries:
            # Combine multiple model queries with should (OR)
            model_filter = {"bool": {"should": model_queries, "minimum_should_match": 1}}
            es_filters.append(model_filter)
            logger.info(f"Applied inclusion model number filters: {model_numbers}")

    # Add model number exclusion filters if provided
    if exclude_model_numbers:
        exclusion_queries = []
        for model in exclude_model_numbers:
            exclusion_queries.append({"wildcard": {model_field: f"{model}*"}})

        if exclusion_queries:
            # Use must_not to exclude these models
            exclusion_filter = {"bool": {"must_not": exclusion_queries}}
            es_filters.append(exclusion_filter)
            logger.info(f"Applied exclusion model number filters: {exclude_model_numbers}")

    return es_filters


def build_field_keyword_query(
    keywords: List[str],
    search_field: str,
    match_type: Literal["match", "match_phrase"] = "match",
    filters: Optional[List[Dict[str, Any]]] = None,
    minimum_should_match: int = 1,
) -> Dict[str, Any]:
    """Build keyword search query for a specific field with optional filters

    Args:
        keywords: List of keywords to search for
        search_field: Field to search in
        match_type: Type of match query ("match" or "match_phrase")
        filters: Optional pre-built filter clauses
        minimum_should_match: Minimum number of keywords that should match

    Returns:
        Elasticsearch query DSL

    """
    # Build should queries for keywords
    should_queries = []
    for keyword in keywords:
        should_queries.append({match_type: {search_field: keyword}})

    # Build bool query
    bool_query = {
        "bool": {
            "should": should_queries,
            "minimum_should_match": minimum_should_match,
        }
    }

    # Add filters if provided
    if filters:
        bool_query["bool"]["filter"] = filters

    # TODO: Add _source fields if needed
    query = {
        "query": bool_query,
    }

    logger.debug(f"Built keyword query for field '{search_field}' with {len(keywords)} keywords")

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
        Elasticsearch KNN query DSL

    """
    if num_candidates is None:
        num_candidates = max(size * 10, 100)

    # Base KNN query structure
    knn_query = {
        "field": field,
        "query_vector": query_embedding,
        "k": size,
        "num_candidates": num_candidates,
    }

    # Add filters if provided
    if filters:
        knn_query["filter"] = {"bool": {"filter": filters}}

    # TODO: Add _source fields if needed
    query = {
        "knn": knn_query,
    }

    logger.info(
        f"Built KNN query with k={size}, num_candidates={num_candidates}, filters={len(filters or [])}"
    )

    return query
