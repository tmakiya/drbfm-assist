from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from src.common.bop import (
    BopConfig,
    BopDataset,
    ChangeRecord,
    detect_changes,
    get_bop_config,
)
from src.common.perf import time_block
from src.common.pfmea import PfmeaDataset
from src.services.change_analysis import build_change_report

from .alignment import build_canonical_alignment
from .baseline import collect_baseline_values, should_suppress_change
from .models import (
    ChangeAnalysisResult,
    ChangePipelineError,
    ComparisonMode,
    ComparisonStats,
    ProgressReporter,
)


def _resolve_variant_row(dataset: BopDataset, variant_id: str) -> pd.Series:
    try:
        return dataset.parts.loc[variant_id]
    except KeyError as exc:
        raise ChangePipelineError(
            f"指定したバリエーションが見つかりません: {variant_id}"
        ) from exc


def _resolve_catalog(dataset: BopDataset, *, allow_empty: bool = False) -> pd.DataFrame:
    if dataset.column_catalog.empty and not allow_empty:
        raise ChangePipelineError(
            "編成表の列カタログが空です。入力データを確認してください。"
        )
    return dataset.column_catalog


def _collect_actionable_changes(
    changes: Sequence[ChangeRecord],
) -> tuple[ChangeRecord, ...]:
    filtered = [change for change in changes if change.change_type != "削除"]
    return tuple(filtered)


class ChangeAnalysisRunner:
    """UI非依存の差分解析ランナー。"""

    def __init__(
        self,
        *,
        bop_config: BopConfig | None = None,
        progress: ProgressReporter | None = None,
        total_steps: int = 3,
    ) -> None:
        self._config = bop_config or get_bop_config()
        self._progress = progress
        self._total_steps = total_steps

    def _report(self, *, completed: int, label: str) -> None:
        if self._progress is None:
            return
        self._progress(completed=completed, total=self._total_steps, label=label)

    def run(
        self,
        variant_label: str,
        source_dataset: BopDataset,
        target_dataset: BopDataset,
        selected_source_variant: str,
        selected_target_variant: str,
        pfmea_dataset: PfmeaDataset,
        *,
        column_keys: Sequence[str] | None = None,
        comparison_mode: ComparisonMode = ComparisonMode.SINGLE_VARIANT,
    ) -> ChangeAnalysisResult:
        source_catalog = _resolve_catalog(source_dataset, allow_empty=True)
        target_catalog = _resolve_catalog(target_dataset, allow_empty=True)

        original_row = _resolve_variant_row(source_dataset, selected_source_variant)
        updated_row = _resolve_variant_row(target_dataset, selected_target_variant)

        (
            canonical_keys,
            source_canonical_catalog,
            target_canonical_catalog,
            canonical_to_source_key,
            canonical_to_target_key,
            target_annotations_canonical,
        ) = build_canonical_alignment(
            source_catalog, target_catalog, target_dataset.annotations
        )

        if column_keys is not None:
            canonical_keys = list(column_keys)

        def _extract_series(
            row: pd.Series, key_map: Mapping[str, str | None]
        ) -> pd.Series:
            values = []
            for canonical_key in canonical_keys:
                original_key = key_map.get(canonical_key)
                if original_key is not None and original_key in row:
                    values.append(row.get(original_key, ""))
                else:
                    values.append("")
            return pd.Series(values, index=canonical_keys)

        original_series = _extract_series(original_row, canonical_to_source_key)
        updated_series = _extract_series(updated_row, canonical_to_target_key)
        baseline_values: dict[str, set[str]] = {}
        if comparison_mode == ComparisonMode.ALL_VARIANTS:
            baseline_values = dict(
                collect_baseline_values(source_dataset.parts, canonical_to_source_key)
            )

        self._report(completed=0, label="解析を開始しています")
        self._report(completed=0, label="変化点を抽出しています")

        with time_block(
            "detect_changes", metadata={"phase": "analysis", "variant": variant_label}
        ):
            changes = detect_changes(
                variant_label,
                original_series,
                updated_series,
                source_canonical_catalog,
                target_canonical_catalog,
                canonical_keys,
                target_annotations_canonical,
                self._config,
            )

        raw_change_count = len(changes)
        suppressed_count = 0
        if comparison_mode == ComparisonMode.ALL_VARIANTS and baseline_values:
            filtered_changes: list[ChangeRecord] = []
            for change in changes:
                if should_suppress_change(change, baseline_values):
                    suppressed_count += 1
                    continue
                filtered_changes.append(change)
            changes = filtered_changes

        source_variant_metadata = (
            source_dataset.metadata.loc[selected_source_variant]
            if selected_source_variant in source_dataset.metadata.index
            else None
        )
        target_variant_metadata = (
            target_dataset.metadata.loc[selected_target_variant]
            if selected_target_variant in target_dataset.metadata.index
            else None
        )

        def _to_clean_dict(series: pd.Series | None) -> dict[str, str]:
            if series is None:
                return {}
            data: dict[str, str] = {}
            for key, value in series.items():
                if pd.isna(value):
                    continue
                text = str(value).strip()
                if text:
                    data[str(key)] = text
            return data

        variant_metadata_payload = {
            "流用元編成表": _to_clean_dict(source_variant_metadata),
            "変更後編成表": _to_clean_dict(target_variant_metadata),
        }

        for change in changes:
            change.variant_metadata = {
                scope: dict(values)
                for scope, values in variant_metadata_payload.items()
            }

        actionable_changes = _collect_actionable_changes(changes)
        self._report(completed=1, label="PFMEA関連情報を集約しています")

        with time_block(
            "build_change_report",
            metadata={"phase": "analysis", "count": len(actionable_changes)},
        ):
            pfmea_report, pfmea_context = build_change_report(
                list(actionable_changes), pfmea_dataset, bop_config=self._config
            )

        self._report(completed=2, label="表示データを整えています")

        self._report(completed=self._total_steps, label="解析が完了しました")

        has_label_mismatch = any(
            change.is_label_mismatch for change in actionable_changes
        )
        comparison_stats = ComparisonStats(
            detected_total=raw_change_count,
            suppressed=suppressed_count,
            retained_total=len(changes),
            actionable=len(actionable_changes),
        )

        return ChangeAnalysisResult(
            comparison_label=variant_label,
            actionable_changes=actionable_changes,
            change_report=pfmea_report,
            pfmea_context=pfmea_context,
            has_label_mismatch=has_label_mismatch,
            comparison_mode=comparison_mode,
            comparison_stats=comparison_stats,
        )


def build_change_analysis(
    variant_label: str,
    source_dataset: BopDataset,
    target_dataset: BopDataset,
    selected_source_variant: str,
    selected_target_variant: str,
    pfmea_dataset: PfmeaDataset,
    *,
    column_keys: Sequence[str] | None = None,
    bop_config: BopConfig | None = None,
    progress: ProgressReporter | None = None,
    comparison_mode: ComparisonMode = ComparisonMode.SINGLE_VARIANT,
) -> ChangeAnalysisResult:
    runner = ChangeAnalysisRunner(bop_config=bop_config, progress=progress)
    return runner.run(
        variant_label,
        source_dataset,
        target_dataset,
        selected_source_variant,
        selected_target_variant,
        pfmea_dataset,
        column_keys=column_keys,
        comparison_mode=comparison_mode,
    )


__all__ = ["ChangeAnalysisRunner", "build_change_analysis"]
