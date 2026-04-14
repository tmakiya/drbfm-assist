"""Workflow execution logic for DRBFM Workflow Application."""

import traceback
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from .client import LangGraphClientError, get_langgraph_client
from .config import settings

# Initial fetch limit for history retrieval.
# We fetch a large fixed number to ensure we get enough threads for grouping.
INITIAL_FETCH_LIMIT = 100

# Timezone for display
JST = ZoneInfo("Asia/Tokyo")


async def fetch_execution_history(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Fetch execution history from LangGraph threads, grouped by batch_id.

    Security: The backend enforces tenant isolation via @auth.on.threads.search,
    which automatically filters results to only include threads belonging to the
    current user's tenant.

    Args:
        limit: Maximum number of items to fetch per page.
        offset: Number of items to skip for pagination.

    Returns a dict with 'items' (list of history items), 'has_more' (bool), and optionally 'error'.
    Items with batch_id are grouped together as a single entry with batch_count > 1.

    """
    try:
        client = get_langgraph_client()
    except LangGraphClientError as e:
        return {"items": [], "has_more": False, "error": str(e)}

    try:
        # Search for threads, sorted by creation time (descending)
        threads = await client.threads.search(
            limit=INITIAL_FETCH_LIMIT,
            offset=offset,
            sort_by="created_at",
            sort_order="desc",
        )

        # First pass: collect thread info and group by batch_id
        batch_groups: dict[str, list[dict[str, Any]]] = {}
        individual_items: list[dict[str, Any]] = []

        for thread in threads:
            thread_id = thread.get("thread_id", "")
            created_at = thread.get("created_at", "")
            metadata = thread.get("metadata", {})

            # Skip legacy threads without tenant_id
            if not metadata.get("tenant_id"):
                logger.bind(thread_id=thread_id).debug(
                    "Skipping legacy thread without tenant_id"
                )
                continue

            # Get runs for this thread
            try:
                runs = await client.runs.list(thread_id=thread_id, limit=1)
            except Exception as e:
                # Skip threads we can't access (permission denied, etc.)
                logger.bind(thread_id=thread_id, error=str(e)).debug(
                    "Skipping thread due to access error"
                )
                continue

            # Get the thread state to extract change_point
            change_point = ""
            status = "unknown"
            result_count = 0
            change_points: list[str] = []
            per_cp_results: list[dict] = []

            if runs:
                run = runs[0]
                status = run.get("status", "unknown")

            try:
                state = await client.threads.get_state(thread_id=thread_id)
                values = state.get("values", {})

                # Check if this is a new-style batch thread (has change_points list)
                change_points = values.get("change_points", [])
                per_cp_results = values.get("per_cp_results", [])

                if change_points:
                    # New batch thread: use first change point as preview
                    change_point = change_points[0] if change_points else ""
                    # Count total results - only use per_cp_results up to change_points count
                    # to avoid counting duplicates from workflow retries
                    valid_results = per_cp_results[: len(change_points)]
                    result_count = sum(
                        len(r.get("relevant_search_results", []))
                        for r in valid_results
                    )
                else:
                    # Old single-change-point thread
                    change_point = values.get("change_point", "")
                    result_count = len(values.get("relevant_search_results", []))
            except Exception:
                pass

            # Format created_at for display (convert to JST)
            display_time = ""
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    jst_dt = dt.astimezone(JST)
                    display_time = jst_dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    display_time = created_at[:16] if len(created_at) >= 16 else created_at

            # Check if this is a new-style batch thread (has change_points, even if results not ready)
            is_new_batch = bool(change_points)

            # For new-style batch, use change_points length; for old-style, use metadata
            batch_total_value = len(change_points) if is_new_batch else int(metadata.get("batch_total", 1))

            thread_info = {
                "thread_id": thread_id,
                "created_at": created_at,
                "display_time": display_time,
                "change_point": change_point,
                "status": status,
                "result_count": result_count,
                "metadata": metadata,
                "batch_id": metadata.get("batch_id"),
                "batch_index": int(metadata.get("batch_index", 0)),
                "batch_total": batch_total_value,
                "is_new_batch": is_new_batch,
                "change_points_count": len(change_points) if is_new_batch else 0,
            }

            # New-style batch threads are complete in themselves - don't group
            if is_new_batch:
                thread_info["batch_count"] = len(change_points)
                individual_items.append(thread_info)
            else:
                # Old-style: group by batch_id
                batch_id = metadata.get("batch_id")
                if batch_id:
                    if batch_id not in batch_groups:
                        batch_groups[batch_id] = []
                    batch_groups[batch_id].append(thread_info)
                else:
                    individual_items.append(thread_info)

        # Second pass: detect incomplete batches and fetch missing threads
        incomplete_batch_ids = []
        for batch_id, batch_threads in batch_groups.items():
            batch_total = batch_threads[0].get("batch_total", 1)
            if len(batch_threads) < batch_total:
                incomplete_batch_ids.append(batch_id)

        # Fetch missing threads for incomplete batches
        for incomplete_batch_id in incomplete_batch_ids:
            try:
                additional_threads = await client.threads.search(
                    metadata={"batch_id": incomplete_batch_id},
                    limit=100,
                )
                # Process additional threads and merge into batch_groups
                for thread in additional_threads:
                    thread_id = thread.get("thread_id", "")
                    # Skip if already in the group
                    existing_ids = {t["thread_id"] for t in batch_groups[incomplete_batch_id]}
                    if thread_id in existing_ids:
                        continue

                    created_at = thread.get("created_at", "")
                    metadata = thread.get("metadata", {})

                    # Get thread state
                    change_point = ""
                    status = "unknown"
                    result_count = 0

                    try:
                        runs = await client.runs.list(thread_id=thread_id, limit=1)
                        if runs:
                            status = runs[0].get("status", "unknown")
                        state = await client.threads.get_state(thread_id=thread_id)
                        values = state.get("values", {})
                        change_point = values.get("change_point", "")
                        result_count = len(values.get("relevant_search_results", []))
                    except Exception:
                        pass

                    display_time = ""
                    if created_at:
                        try:
                            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            jst_dt = dt.astimezone(JST)
                            display_time = jst_dt.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            display_time = created_at[:16] if len(created_at) >= 16 else created_at

                    batch_groups[incomplete_batch_id].append({
                        "thread_id": thread_id,
                        "created_at": created_at,
                        "display_time": display_time,
                        "change_point": change_point,
                        "status": status,
                        "result_count": result_count,
                        "metadata": metadata,
                        "batch_id": metadata.get("batch_id"),
                        "batch_index": int(metadata.get("batch_index", 0)),
                        "batch_total": int(metadata.get("batch_total", 1)),
                    })
            except Exception as e:
                logger.bind(batch_id=incomplete_batch_id, error=str(e)).warning(
                    "Failed to fetch additional threads for incomplete batch"
                )

        # Third pass: create history items
        history_items = []

        # Process batch groups
        for batch_id, batch_threads in batch_groups.items():
            batch_total = batch_threads[0].get("batch_total", 1)

            # Sort by batch_index to get first item
            batch_threads.sort(key=lambda x: x["batch_index"])
            first_thread = batch_threads[0]

            # Aggregate status (error if any failed, success if all succeeded)
            statuses = [t["status"] for t in batch_threads]
            if "error" in statuses:
                aggregated_status = "error"
            elif all(s == "success" for s in statuses):
                aggregated_status = "success"
            elif "running" in statuses or "pending" in statuses:
                aggregated_status = "running"
            else:
                aggregated_status = "pending"

            # Check if batch is incomplete
            is_incomplete = len(batch_threads) < batch_total
            is_running = aggregated_status in ("running", "pending")

            # Skip incomplete batches only if they're not running
            if is_incomplete and not is_running:
                logger.bind(
                    batch_id=batch_id,
                    batch_total=batch_total,
                    actual_count=len(batch_threads),
                ).debug("Skipping incomplete non-running batch")
                continue

            # Sum up result counts
            total_result_count = sum(t["result_count"] for t in batch_threads)

            # Create batch summary with first change_point as preview
            history_items.append({
                "thread_id": first_thread["thread_id"],  # Use first thread as representative
                "batch_id": batch_id,
                "batch_count": len(batch_threads),
                "batch_total": batch_total,
                "created_at": first_thread["created_at"],
                "display_time": first_thread["display_time"],
                "change_point": first_thread["change_point"],  # First item's change_point
                "status": aggregated_status,
                "result_count": total_result_count,
                "metadata": first_thread["metadata"],
            })

        # Add individual items (no batch_id)
        for item in individual_items:
            item["batch_id"] = None
            item["batch_count"] = 1
            history_items.append(item)

        # Sort all items by created_at descending
        history_items.sort(key=lambda x: x["created_at"], reverse=True)

        # Apply limit after grouping
        history_items = history_items[:limit]

        # Check if there might be more results
        has_more = len(threads) == INITIAL_FETCH_LIMIT

        return {"items": history_items, "has_more": has_more, "error": None}

    except Exception as e:
        error_msg = str(e) if str(e) else type(e).__name__
        logger.bind(error=error_msg, traceback=traceback.format_exc()).error(
            "Failed to fetch execution history"
        )
        return {"items": [], "has_more": False, "error": f"履歴取得エラー: {error_msg}"}


async def load_thread_results(thread_id: str) -> Optional[dict[str, Any]]:
    """Load results from a specific thread.

    Security: The backend enforces tenant isolation via @auth.on.threads.read.
    This function will receive a 403 error if the thread belongs to a different tenant.
    """
    try:
        client = get_langgraph_client()
    except LangGraphClientError:
        return None

    try:
        state = await client.threads.get_state(thread_id=thread_id)
        return state.get("values", {})
    except Exception as e:
        error_str = str(e)
        # Log security-related errors at warning level
        if "403" in error_str or "Access denied" in error_str:
            logger.bind(thread_id=thread_id, error=error_str).warning(
                "Access denied when loading thread results (tenant isolation)"
            )
        else:
            logger.bind(thread_id=thread_id, error=error_str).error(
                "Failed to load thread results"
            )
        return None


async def run_drbfm_workflow(
    change: str,
    top_k: int = 5,
    search_size: int = 10,
    batch_id: Optional[str] = None,
    batch_index: int = 0,
    batch_total: int = 1,
) -> dict[str, Any]:
    """Run a single DRBFM workflow with the given change point using LangGraph SDK.

    Args:
        change: The change point text to analyze.
        top_k: Number of top results to keep per change point.
        search_size: Number of search results to retrieve per search.
        batch_id: Optional batch ID to group related workflows together.
        batch_index: Index of this workflow within the batch (0-based).
        batch_total: Total number of workflows in the batch.

    Returns:
        Workflow result dictionary with search results and estimations.

    """
    # Get client instance
    try:
        client = get_langgraph_client()
    except LangGraphClientError as e:
        return {"error": str(e)}

    logger.bind(
        batch_id=batch_id, batch_index=batch_index, top_k=top_k, search_size=search_size
    ).debug("Starting DRBFM workflow")

    try:
        # Create input for the graph (data only)
        input_data = {
            "change_point": change,
        }

        # Pass configuration via configurable (LangGraph best practice)
        config = {
            "configurable": {
                "top_k": top_k,
                "search_size": search_size,
            }
        }

        # Create thread with batch metadata for grouping
        thread_metadata: dict[str, str] = {}
        if batch_id:
            thread_metadata["batch_id"] = batch_id
            thread_metadata["batch_index"] = str(batch_index)
            thread_metadata["batch_total"] = str(batch_total)

        # Create thread and run
        thread = await client.threads.create(metadata=thread_metadata if thread_metadata else None)
        run = await client.runs.create(
            thread_id=thread["thread_id"],
            assistant_id=settings.graph_id,
            input=input_data,
            config=config,
        )

        # Wait for completion
        await client.runs.join(thread_id=thread["thread_id"], run_id=run["run_id"])

        # Check run status for errors
        final_run = await client.runs.get(thread_id=thread["thread_id"], run_id=run["run_id"])
        if final_run.get("status") == "error":
            error_detail = final_run.get("error", "Unknown error")
            raise RuntimeError(f"Run failed: {error_detail}")

        # Get the final state
        state = await client.threads.get_state(thread_id=thread["thread_id"])

        values = state["values"]
        logger.bind(
            batch_id=batch_id,
            batch_index=batch_index,
            state_keys=list(values.keys()) if values else [],
            relevant_results_count=len(values.get("relevant_search_results", [])) if values else 0,
            estimation_results_count=len(values.get("estimation_results", {})) if values else 0,
        ).info("Workflow completed successfully")
        return values

    except Exception as e:
        error_msg = f"ワークフロー実行エラー: {str(e)}"
        logger.bind(
            batch_id=batch_id,
            batch_index=batch_index,
            error=error_msg,
            traceback=traceback.format_exc(),
        ).error("DRBFM workflow failed")
        return {
            "relevant_search_results": [],
            "estimation_results": {},
            "query_attributes": None,
            "search_history": [],
            "error": error_msg,
        }


async def load_batch_results(batch_id: str) -> list[dict[str, Any]]:
    """Load all results from threads belonging to a specific batch.

    Args:
        batch_id: The batch ID to load results for.

    Returns:
        List of result dictionaries sorted by batch_index, each containing
        the workflow values and metadata.

    """
    try:
        client = get_langgraph_client()
    except LangGraphClientError:
        return []

    try:
        # Search for threads with the given batch_id in metadata
        threads = await client.threads.search(
            metadata={"batch_id": batch_id},
            limit=100,  # Reasonable upper limit for batch size
        )

        if not threads:
            logger.bind(batch_id=batch_id).warning("No threads found for batch")
            return []

        results = []
        for thread in threads:
            thread_id = thread.get("thread_id", "")
            metadata = thread.get("metadata", {})
            batch_index = int(metadata.get("batch_index", 0))

            try:
                state = await client.threads.get_state(thread_id=thread_id)
                values = state.get("values", {})
                results.append({
                    "thread_id": thread_id,
                    "batch_index": batch_index,
                    "change_point": values.get("change_point", ""),
                    "values": values,
                })
            except Exception as e:
                logger.bind(thread_id=thread_id, error=str(e)).warning(
                    "Failed to load thread state"
                )
                continue

        # Sort by batch_index to maintain original order
        results.sort(key=lambda x: x["batch_index"])

        logger.bind(batch_id=batch_id, count=len(results)).info(
            "Loaded batch results successfully"
        )
        return results

    except Exception as e:
        logger.bind(batch_id=batch_id, error=str(e), traceback=traceback.format_exc()).error(
            "Failed to load batch results"
        )
        return []


async def run_drbfm_workflows_batch(
    changes: list[dict[str, str]],
    top_k: int = 5,
    search_size: int = 10,
    batch_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Run multiple DRBFM workflows in parallel using backend Send API.

    Single API call to backend, which handles parallel processing internally.
    If the page is reloaded, the workflow continues on the backend and
    results can be retrieved from history.

    Args:
        changes: List of change point dicts with 'change' key.
        top_k: Number of top results per change point.
        search_size: Number of search results per search.
        batch_id: Optional batch ID for history tracking.

    Returns:
        List of workflow results in the same order as inputs.

    """
    try:
        client = get_langgraph_client()
    except LangGraphClientError as e:
        # Return error for all inputs
        return [
            {
                "relevant_search_results": [],
                "estimation_results": {},
                "error": str(e),
            }
            for _ in changes
        ]

    batch_total = len(changes)
    logger.bind(batch_id=batch_id, batch_total=batch_total, top_k=top_k, search_size=search_size).info(
        "Starting batch DRBFM workflow"
    )

    try:
        # Create input for batch graph - list of change points
        change_points = [c["change"] for c in changes]
        input_data = {"change_points": change_points}

        # Pass configuration via configurable
        config = {
            "configurable": {
                "top_k": top_k,
                "search_size": search_size,
            }
        }

        # Thread metadata for history tracking
        thread_metadata: dict[str, str] = {
            "batch_total": str(batch_total),
        }
        if batch_id:
            thread_metadata["batch_id"] = batch_id

        # Create thread and run using batch graph
        thread = await client.threads.create(metadata=thread_metadata)
        run = await client.runs.create(
            thread_id=thread["thread_id"],
            assistant_id="drassist-batch",  # Use batch graph
            input=input_data,
            config=config,
        )

        # Wait for completion
        await client.runs.join(thread_id=thread["thread_id"], run_id=run["run_id"])

        # Check run status for errors
        final_run = await client.runs.get(thread_id=thread["thread_id"], run_id=run["run_id"])
        if final_run.get("status") == "error":
            error_detail = final_run.get("error", "Unknown error")
            raise RuntimeError(f"Run failed: {error_detail}")

        # Get the final state
        state = await client.threads.get_state(thread_id=thread["thread_id"])
        values = state.get("values", {})

        # Extract per_cp_results - already sorted by index in backend
        per_cp_results = values.get("per_cp_results", [])

        logger.bind(
            batch_id=batch_id,
            batch_total=batch_total,
            results_count=len(per_cp_results),
        ).info("Batch workflow completed successfully")

        # Return results in order (backend already sorted by index)
        return per_cp_results

    except Exception as e:
        error_msg = f"バッチワークフロー実行エラー: {str(e)}"
        logger.bind(
            batch_id=batch_id,
            batch_total=batch_total,
            error=error_msg,
            traceback=traceback.format_exc(),
        ).error("Batch DRBFM workflow failed")

        # Return error for all inputs
        return [
            {
                "relevant_search_results": [],
                "estimation_results": {},
                "error": error_msg,
            }
            for _ in changes
        ]
