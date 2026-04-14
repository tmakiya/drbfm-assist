"""DataFrame processing for DRBFM Workflow Application."""

from typing import Any

import pandas as pd
from loguru import logger

from .client import get_tenant_id_from_request
from .config import settings
from .formatters import format_reasoning_chains_as_markdown


def _normalize_to_string(value: Any) -> str:
    """Normalize a value to a string, joining list items with comma.

    Args:
        value: The value to normalize (can be str, list, or None).

    Returns:
        A string representation of the value.

    """
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value)


def _get_drawer_host() -> str:
    """Get Drawer host from the current request URL.

    Returns:
        The Drawer base URL derived from the current request host.

    """
    import streamlit as st

    try:
        # Get the current request host from headers
        headers = st.context.headers
        host = headers.get("Host", "")
        if host:
            # Use the same protocol and host as the Streamlit app
            # Drawer is served from the same host
            return f"https://{host}"
    except Exception as e:
        logger.bind(error=str(e)).debug("Could not get host from request headers")

    # Fallback to configured base URL
    return settings.drawer_base_url


def _build_drawer_url(original_id: str) -> str:
    """Build DrawerURL using tenant_id from internal token.

    Args:
        original_id: The document's original ID.

    Returns:
        The full DrawerURL or empty string if original_id is not provided.

    """
    if not original_id:
        return ""

    tenant_id = get_tenant_id_from_request()
    if not tenant_id:
        logger.warning("tenant_id not found in request, DrawerURL will be empty")
        return ""

    drawer_host = _get_drawer_host()
    return f"{drawer_host}/{tenant_id}/documents/{original_id}"


def create_output_rows(change: str, result: dict[str, Any], row_id: int) -> list[dict[str, Any]]:
    """Create output rows from workflow results."""
    output_rows = []

    # Extract workflow results
    search_results = result.get("relevant_search_results", [])
    estimation_results = result.get("estimation_results", {})
    error = result.get("error")

    # Debug logging for estimation_results
    est_keys = list(estimation_results.keys()) if isinstance(estimation_results, dict) else None
    logger.bind(
        row_id=row_id,
        estimation_results_type=type(estimation_results).__name__,
        estimation_results_keys=est_keys,
        estimation_results_len=len(estimation_results) if estimation_results else 0,
        search_results_count=len(search_results),
    ).info("Processing workflow result")

    if error:
        logger.bind(row_id=row_id, error=error).warning("Error detected in workflow result")

    # If no search results, create one row with empty search result fields
    if not search_results:
        output_row = {
            "ID": row_id,
            "変更": change,
            "推定不具合_内容": "",
            "推定不具合_原因": "",
            "推定不具合_対策": "",
            "推定不具合_根拠": "",
            "DrawerURL": "",
            "検索結果_ユニット": "",
            "検索結果_部位": "",
            "検索結果_変更": "",
            "検索結果_故障モード": "",
            "検索結果_故障影響": "",
            "検索結果_対策": "",
        }
        output_rows.append(output_row)
    else:
        # Create one row per search result
        for result_item in search_results:
            doc_id = result_item.get("doc_id", "")
            # Convert doc_id to string for consistent key lookup
            # (estimation_results keys are strings, but doc_id may be int)
            doc_id_str = str(doc_id) if doc_id else ""

            # Get estimation result
            estimation_data = {}
            doc_id_found = doc_id_str in estimation_results if isinstance(estimation_results, dict) else False
            logger.bind(
                row_id=row_id,
                doc_id=doc_id,
                doc_id_str=doc_id_str,
                doc_id_found=doc_id_found,
            ).debug("Looking up estimation for doc_id")

            if doc_id_found:
                estimation_result = estimation_results[doc_id_str]
                logger.bind(
                    doc_id=doc_id_str,
                    estimation_result_type=type(estimation_result).__name__,
                ).debug("Found estimation result")
                if hasattr(estimation_result, "model_dump"):
                    estimation_data = estimation_result.model_dump()
                else:
                    estimation_data = estimation_result

            # Generate DrawerURL using tenant_id from internal token
            original_id = result_item.get("original_id", "")
            drawer_url = _build_drawer_url(original_id)

            output_row = {
                "ID": row_id,
                "変更": change,
                "推定不具合_内容": estimation_data.get("potential_defect", ""),
                "推定不具合_原因": estimation_data.get("potential_cause", ""),
                "推定不具合_対策": estimation_data.get("countermeasure", ""),
                "推定不具合_根拠": format_reasoning_chains_as_markdown(
                    estimation_data.get("reasoning_chains", [])
                ),
                "DrawerURL": drawer_url,
                "検索結果_ユニット": _normalize_to_string(result_item.get("cause", {}).get("unit")),
                "検索結果_部位": _normalize_to_string(result_item.get("cause", {}).get("part")),
                "検索結果_変更": _normalize_to_string(result_item.get("cause", {}).get("part_change")),
                "検索結果_故障モード": _normalize_to_string(result_item.get("failure", {}).get("mode")),
                "検索結果_故障影響": _normalize_to_string(result_item.get("failure", {}).get("effect")),
                "検索結果_対策": _normalize_to_string(result_item.get("countermeasures")),
            }
            output_rows.append(output_row)

    return output_rows


def create_output_dataframe(inputs: list[dict[str, str]], results: list[dict[str, Any]]) -> pd.DataFrame:
    """Create a complete output DataFrame from all workflow results."""
    all_output_rows = []

    for i, (input_data, result) in enumerate(zip(inputs, results)):
        output_rows = create_output_rows(change=input_data["change"], result=result, row_id=i + 1)
        all_output_rows.extend(output_rows)

    return pd.DataFrame(all_output_rows)
