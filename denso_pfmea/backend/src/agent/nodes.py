"""PFMEA Workflow Nodes for LangGraph.

Each node represents a step in the PFMEA AI assessment workflow.
All nodes are async for optimal LangGraph integration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from langchain_core.language_models import BaseChatModel

from src.agent.llm_result_parser import RatingTarget, parse_change_entry
from src.agent.risk_rating_builder import build_risk_rating_groups
from src.agent.state import PfmeaWorkflowState
from src.common.bop import ChangeRecord
from src.common.pfmea.models import ProcessSummary
from src.llm.gemini_client import create_gemini_client
from src.services.llm_batch_runner import run_llm_batch_async
from src.services.pfmea.risk_rating import (
    RiskRatingRecord,
    aevaluate_risk_ratings,
)
from src.services.pfmea_ai import PFMEA_AI_COLUMN_MAP
from src.services.pfmea_context import PfmeaContext

logger = logging.getLogger(__name__)


def _reconstruct_process_summary(summary_dict: Dict[str, Any]) -> ProcessSummary:
    """Reconstruct ProcessSummary object from serialized dictionary."""
    # extra_sections の値を tuple に変換
    extra_sections_raw = summary_dict.get("extra_sections", {}) or {}
    extra_sections = {
        k: tuple(v) if isinstance(v, list) else v for k, v in extra_sections_raw.items()
    }

    return ProcessSummary(
        process_name=summary_dict.get("process_name", ""),
        anchor_row=summary_dict.get("anchor_row", 0),
        raw_text=summary_dict.get("raw_text", ""),
        functions=tuple(summary_dict.get("functions", [])),
        requirements=tuple(summary_dict.get("requirements", [])),
        extra_sections=extra_sections,
    )


def _reconstruct_pfmea_context(
    context_dict: Dict[str, Any],
) -> Dict[str, PfmeaContext | None]:
    """Reconstruct PfmeaContext objects from serialized dictionary.

    NOTE: Frontend から送られてくる data は List[Dict] 形式のため、
    pd.DataFrame に変換する必要がある。
    summaries も Dict[str, Dict] 形式のため、ProcessSummary に変換する。
    """
    import pandas as pd

    result: Dict[str, PfmeaContext | None] = {}
    for change_id, ctx_data in context_dict.items():
        if ctx_data is None:
            result[change_id] = None
        else:
            # data が List[Dict] の場合は DataFrame に変換
            data = ctx_data.get("data")
            if data is not None and isinstance(data, list):
                data = pd.DataFrame(data)

            # summaries を ProcessSummary オブジェクトに変換
            summaries_raw = ctx_data.get("summaries") or {}
            summaries: Dict[str, ProcessSummary] = {}
            for process_name, summary_data in summaries_raw.items():
                if isinstance(summary_data, dict):
                    summaries[process_name] = _reconstruct_process_summary(summary_data)
                # 既に ProcessSummary の場合はそのまま使用
                elif isinstance(summary_data, ProcessSummary):
                    summaries[process_name] = summary_data

            # PfmeaContext is a simple dataclass, reconstruct it
            result[change_id] = PfmeaContext(
                block=ctx_data.get("block"),
                data=data,
                summaries=summaries,
            )
    return result


async def _create_llm_client_async(state: PfmeaWorkflowState) -> BaseChatModel:
    """Create a LangChain ChatModel in a separate thread to avoid blocking.

    ChatGoogleGenerativeAI の初期化時に google.auth.default() が呼ばれ、
    これが subprocess を使用するため、asyncio.to_thread でラップして
    イベントループをブロックしないようにする。
    """
    return await asyncio.to_thread(
        create_gemini_client,
        model_name=state.selected_model,
    )


async def prefetch_pfmea_mappings(state: PfmeaWorkflowState) -> Dict[str, Any]:
    """Prefetch PFMEA function mappings.

    This node prepares the PFMEA context for the assessment phase.
    In the original implementation, this was done via ensure_function_mappings.
    For simplicity in the LangGraph version, we skip the caching and
    let the assessment phase handle the context directly.
    """
    logger.info("prefetch_pfmea_mappings: Starting with %d changes", len(state.changes))

    return {
        "current_phase": "mapping",
        "phase_message": "PFMEA機能マッピングを準備しています",
        "total_count": len(state.changes),
        "completed_count": 0,
    }


def _dict_to_change_record(change_dict: Dict[str, Any]) -> ChangeRecord:
    """Convert a dictionary to a ChangeRecord object."""
    return ChangeRecord(
        variant_id=change_dict.get("variant_id", ""),
        block=change_dict.get("block", ""),
        station=change_dict.get("station", ""),
        part_label=change_dict.get("part_label", ""),
        column_key=change_dict.get("column_key", ""),
        original_value=change_dict.get("original_value", ""),
        new_value=change_dict.get("new_value", ""),
        change_type=change_dict.get("change_type", ""),
        keywords=change_dict.get("keywords", []),
        change_id=change_dict.get("change_id", ""),
        original_part_label=change_dict.get("original_part_label"),
        updated_part_label=change_dict.get("updated_part_label"),
        is_label_mismatch=change_dict.get("is_label_mismatch", False),
        shape_feature=change_dict.get("shape_feature"),
        preceding_part_label=change_dict.get("preceding_part_label"),
        following_part_label=change_dict.get("following_part_label"),
        preceding_original_value=change_dict.get("preceding_original_value"),
        preceding_new_value=change_dict.get("preceding_new_value"),
        following_original_value=change_dict.get("following_original_value"),
        following_new_value=change_dict.get("following_new_value"),
        variant_metadata=change_dict.get("variant_metadata", {}),
    )


async def execute_llm_assessment(state: PfmeaWorkflowState) -> Dict[str, Any]:
    """Execute LLM assessment for all changes.

    This node runs the PFMEA AI assessment using the Gemini model.
    Uses asyncio.gather for parallel LLM calls.
    """
    logger.info("execute_llm_assessment: Processing %d changes", len(state.changes))

    if not state.changes:
        return {
            "current_phase": "assessment_complete",
            "phase_message": "評価対象がありません",
            "assessment_results": {},
            "completed_count": 0,
        }

    # Create LangChain ChatModel (in separate thread to avoid blocking)
    client = await _create_llm_client_async(state)

    # Reconstruct PfmeaContext from serialized data
    pfmea_context = _reconstruct_pfmea_context(state.pfmea_context)

    # Convert state.changes (List[Dict]) to List[ChangeRecord]
    change_records = [_dict_to_change_record(change) for change in state.changes]

    # Run batch assessment (async version)
    try:
        batch_results = await run_llm_batch_async(
            client,
            change_records,
            pfmea_context,
            max_concurrency=4,
            progress_callback=None,  # Progress is tracked via state
        )
    except Exception as e:
        logger.exception("LLM assessment failed")
        return {
            "current_phase": "error",
            "error": f"AI推定の実行に失敗しました: {e}",
            "error_code": "assessment_failed",
        }

    return {
        "current_phase": "assessment_complete",
        "phase_message": f"AI推定が完了しました（{len(batch_results)}件）",
        "assessment_results": batch_results,
        "completed_count": len(batch_results),
    }


async def execute_risk_rating(state: PfmeaWorkflowState) -> Dict[str, Any]:
    """Execute risk rating for assessment results.

    This node evaluates S/O/D (Severity/Occurrence/Detection) ratings.
    Uses asyncio.gather for parallel LLM calls.
    """
    logger.info("execute_risk_rating: Processing assessment results")

    if not state.assessment_results:
        return {
            "current_phase": "rating_complete",
            "phase_message": "リスク評価対象がありません",
            "risk_ratings": {},
            "rating_targets_lookup": {},
        }

    # Reconstruct PfmeaContext from serialized data
    pfmea_context = _reconstruct_pfmea_context(state.pfmea_context)

    # Parse assessment results to build rating targets
    rating_targets: List[RatingTarget] = []

    for change_id, result in state.assessment_results.items():
        if result.get("status") != "success":
            continue

        # Get the change data
        change_data = None
        for change in state.changes:
            if change.get("change_id") == change_id:
                change_data = change
                break

        if change_data is None:
            continue

        # Parse the entry to get rating targets
        parsed = parse_change_entry(change_data, result)
        rating_targets.extend(parsed.rating_targets)

    if not rating_targets:
        return {
            "current_phase": "rating_complete",
            "phase_message": "リスク評価対象がありません",
            "risk_ratings": {},
            "rating_targets_lookup": {},
        }

    # Build rating groups from targets
    rating_groups, target_lookup = build_risk_rating_groups(
        rating_targets, pfmea_context
    )

    logger.info(
        "execute_risk_rating: Built %d rating groups from %d targets",
        len(rating_groups),
        len(rating_targets),
    )

    if not rating_groups:
        return {
            "current_phase": "rating_complete",
            "phase_message": "リスク評価グループがありません",
            "risk_ratings": {},
            "rating_targets_lookup": {},
        }

    # Create LangChain ChatModel for risk rating (in separate thread to avoid blocking)
    client = await _create_llm_client_async(state)

    try:
        ratings = await aevaluate_risk_ratings(
            client,
            rating_groups,
            progress_callback=None,
        )
    except Exception as e:
        logger.exception("Risk rating failed")
        return {
            "current_phase": "error",
            "error": f"リスク評価の実行に失敗しました: {e}",
            "error_code": "rating_failed",
        }

    # Convert RiskRatingRecord to serializable dict
    serialized_ratings: Dict[str, Dict[str, Any]] = {}
    for key, record in ratings.items():
        if isinstance(record, RiskRatingRecord):
            serialized_ratings[key] = {
                "rating_id": record.rating_id,
                "impact": record.impact,
                "occurrence": record.occurrence,
                "detection": record.detection,
                "rationale": record.rationale,
                "impact_reason": record.impact_reason,
                "occurrence_reason": record.occurrence_reason,
                "detection_reason": record.detection_reason,
                "formatted_rationale": record.formatted_indicator_rationale(),
            }
        else:
            serialized_ratings[key] = record

    # Serialize target_lookup for use in aggregate_results
    serialized_lookup: Dict[str, Dict[str, Any]] = {}
    for key, target in target_lookup.items():
        serialized_lookup[key] = {
            "change_id": target.change_id,
            "rating_id": target.rating_id,
            "row": target.row,
        }

    return {
        "current_phase": "rating_complete",
        "phase_message": f"リスク評価が完了しました（{len(ratings)}件）",
        "risk_ratings": serialized_ratings,
        "rating_targets_lookup": serialized_lookup,
    }


def _merge_change_metadata(
    change: Dict[str, Any], row: Dict[str, str]
) -> Dict[str, str]:
    """Merge change metadata with parsed row information.

    This is equivalent to the original merge_change_metadata function
    from llm_result_parser.py.
    """
    payload = {
        "バリエーション": change.get("variant_id", ""),
        "ブロック": change.get("block", ""),
        "ステーション": change.get("station", ""),
        "対象部品": change.get("part_label", ""),
        "変更種別": change.get("change_type", ""),
    }
    merged = {**payload, **row}
    return {
        key: ("" if value is None else str(value).strip())
        for key, value in merged.items()
    }


def _apply_column_mapping(row: Dict[str, str]) -> Dict[str, str]:
    """Apply PFMEA_AI_COLUMN_MAP to normalize column names.

    Maps LLM output column names to standard PFMEA column names.
    """
    mapped = {}
    for key, value in row.items():
        # Check if this key needs to be mapped
        mapped_key = PFMEA_AI_COLUMN_MAP.get(key, key)
        mapped[mapped_key] = value
    return mapped


async def aggregate_results(state: PfmeaWorkflowState) -> Dict[str, Any]:
    """Aggregate all results into final output format.

    This node combines assessment results and risk ratings into
    the final structured output.
    """
    logger.info("aggregate_results: Aggregating final results")

    structured_rows: List[Dict[str, str]] = []
    rows_by_change: Dict[str, List[Dict[str, str]]] = {}

    # Build a lookup for change data by change_id
    changes_by_id: Dict[str, Dict[str, Any]] = {}
    for change in state.changes:
        change_id = change.get("change_id", "")
        if change_id:
            changes_by_id[change_id] = change

    # Parse assessment results and merge with risk ratings
    for change_id, result in state.assessment_results.items():
        if result.get("status") != "success":
            continue

        content = result.get("content", "")
        if not content:
            continue

        # Parse JSON content
        import json

        try:
            data = json.loads(content)
            results_list = data.get("results", [])
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON for change %s", change_id)
            continue

        # Get the change data for metadata
        change_data = changes_by_id.get(change_id, {})

        change_rows: List[Dict[str, str]] = []
        for row in results_list:
            # Convert to string values
            row_dict = {k: str(v) if v is not None else "" for k, v in row.items()}

            # Apply column name mapping (e.g., "機能" -> "工程の機能")
            row_dict = _apply_column_mapping(row_dict)

            # Merge risk ratings if available
            # Try multiple key formats to find the rating
            rating_id = row.get("追加検討ID", "")
            rating = None

            # Try direct key format first
            for key, r in state.risk_ratings.items():
                if key.endswith(f":{rating_id}"):
                    rating = r
                    break

            # Fallback: try matching by rating_id in the record
            if rating is None:
                for key, r in state.risk_ratings.items():
                    if isinstance(r, dict) and r.get("rating_id") == rating_id:
                        rating = r
                        break

            if rating:
                row_dict["影響度合"] = str(rating.get("impact", ""))
                row_dict["発生度合"] = str(rating.get("occurrence", ""))
                row_dict["検出度合"] = str(rating.get("detection", ""))
                rpn = (
                    rating.get("impact", 0)
                    * rating.get("occurrence", 0)
                    * rating.get("detection", 0)
                )
                row_dict["重要度（RPN）"] = str(rpn) if rpn else ""
                # Add RPN evaluation reason
                formatted_rationale = rating.get("formatted_rationale", "")
                if formatted_rationale:
                    row_dict["RPN評価理由"] = formatted_rationale

            # Merge change metadata (ブロック, ステーション, 対象部品, 変更種別)
            row_dict = _merge_change_metadata(change_data, row_dict)

            change_rows.append(row_dict)
            structured_rows.append(row_dict)

        rows_by_change[change_id] = change_rows

    return {
        "current_phase": "complete",
        "phase_message": f"処理が完了しました（{len(structured_rows)}行）",
        "structured_rows": structured_rows,
        "rows_by_change": rows_by_change,
    }


__all__ = [
    "prefetch_pfmea_mappings",
    "execute_llm_assessment",
    "execute_risk_rating",
    "aggregate_results",
]
