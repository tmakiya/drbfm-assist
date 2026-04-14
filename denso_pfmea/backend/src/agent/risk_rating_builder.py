"""Build risk rating groups from parsed LLM results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Tuple

from src.services.pfmea.baseline_examples import collect_baseline_examples
from src.services.pfmea.risk_rating import RiskRatingGroup, RiskRatingRow
from src.services.pfmea_context import PfmeaContext

from .llm_result_parser import (
    RatingTarget,
    compose_additional_notes,
    summarize_change_metadata,
)


def build_risk_rating_groups(
    rating_targets: Sequence[RatingTarget],
    pfmea_context: Mapping[str, PfmeaContext | None],
) -> Tuple[Tuple[RiskRatingGroup, ...], Dict[str, RatingTarget]]:
    """Aggregate rating targets into RiskRatingGroup payloads."""
    if not rating_targets:
        return (), {}

    group_builders: Dict[str, Dict[str, Any]] = {}
    target_lookup: Dict[str, RatingTarget] = {}

    for target in rating_targets:
        builder = group_builders.setdefault(
            target.group_id,
            {
                "process_name": target.process_name or "(工程名未設定)",
                "process_function": target.function_text or "(工程の機能未設定)",
                "assurances": [],
                "rows": [],
                "changes": [],
                "contexts": [],
                "change_rows": {},
            },
        )
        if target.process_name:
            builder["process_name"] = target.process_name
        if target.function_text:
            builder["process_function"] = target.function_text

        for assurance in target.assurances:
            if assurance and assurance not in builder["assurances"]:
                builder["assurances"].append(assurance)

        additional_notes = compose_additional_notes(target.row)
        risk_row = RiskRatingRow(
            rating_id=target.rating_id,
            requirement=str(target.row.get("要求事項（良品条件）", "") or ""),
            failure_mode=str(target.row.get("工程故障モード", "") or ""),
            effect=str(target.row.get("故障の影響", "") or ""),
            cause=str(target.row.get("故障の原因およびメカニズム", "") or ""),
            judgement=str(target.row.get("判断", "") or ""),
            reason=str(target.row.get("追加理由", "") or ""),
            prevention=str(target.row.get("予防", "") or ""),
            detection_method=str(target.row.get("検出方法", "") or ""),
            recommended_action=str(target.row.get("推奨処置", "") or ""),
            additional_notes=additional_notes,
        )
        builder["rows"].append(risk_row)
        builder["changes"].append(target.change)
        builder["change_rows"].setdefault(target.change_id, []).append(risk_row)

        context_bundle = pfmea_context.get(target.change_id)
        if context_bundle is not None:
            contexts = builder["contexts"]
            if all(context is not context_bundle for context in contexts):
                contexts.append(context_bundle)

        target_lookup[f"{target.group_id}:{target.rating_id}"] = target

    rating_groups: List[RiskRatingGroup] = []
    for group_id, builder in group_builders.items():
        contexts = tuple(builder.get("contexts", []))
        change_summaries: List[str] = []
        seen_changes: set[str] = set()
        for change in builder.get("changes", []):
            # Handle both dict and object-like change
            if isinstance(change, dict):
                change_id = change.get("change_id", "")
            else:
                change_id = getattr(change, "change_id", "")
            if change_id in seen_changes:
                continue
            seen_changes.add(change_id)
            change_rows = builder.get("change_rows", {}).get(change_id, [])
            change_summaries.append(summarize_change_metadata(change, change_rows))

        baseline_examples = collect_baseline_examples(
            contexts,
            process_name=builder["process_name"],
        )
        rating_groups.append(
            RiskRatingGroup(
                group_id=group_id,
                process_name=builder["process_name"],
                process_function=builder["process_function"],
                assurances=tuple(builder["assurances"]),
                rows=tuple(builder["rows"]),
                change_summaries=tuple(change_summaries),
                baseline_examples=baseline_examples,
            )
        )

    return tuple(rating_groups), target_lookup


__all__ = ["build_risk_rating_groups"]
