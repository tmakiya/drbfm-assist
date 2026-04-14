"""Change impact analysis helpers (PFMEAマッチング・レポート生成)."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.common.bop import BopConfig, ChangeRecord, get_bop_config
from src.common.concurrency import parallel_map
from src.common.perf import time_block
from src.common.pfmea import PfmeaDataset
from src.services.pfmea_context import PfmeaContext


def _ensure_config(config: BopConfig | None) -> BopConfig:
    return config or get_bop_config()


def _resolve_pfmea_block(
    block_name: str, candidate_blocks: Iterable[str]
) -> str | None:
    text = (block_name or "").strip()
    for candidate in candidate_blocks:
        if candidate in text:
            return candidate
    return None


def match_pfmea(
    change: ChangeRecord,
    pfmea_dataset: PfmeaDataset,
    *,
    bop_config: BopConfig | None = None,
) -> pd.DataFrame:
    """PFMEA候補行をキーワードベースで抽出し、関連度順に整列して返す。"""
    conf = _ensure_config(bop_config)
    block_key = _resolve_pfmea_block(change.block, pfmea_dataset.by_block.keys())
    if block_key is None:
        return pd.DataFrame()
    pfmea_df = pfmea_dataset.by_block.get(block_key, pd.DataFrame())
    if pfmea_df.empty:
        return pfmea_df

    process_rules = conf.process_rules
    candidates = set()
    for process_name, keywords in process_rules:
        if any(keyword in change.part_label for keyword in keywords):
            candidates.add(process_name)
    if not candidates and "嵌合" in change.block:
        candidates.add("ｹｰｽ嵌合")
    if not candidates:
        candidates = set(pfmea_df["process_name"].unique())

    filtered = pfmea_df[pfmea_df["process_name"].isin(candidates)].copy()
    if filtered.empty:
        return filtered

    keyword_set = change.keywords or []
    pattern_texts = filtered.apply(
        lambda row: " ".join(
            [
                row.get("failure_mode", ""),
                row.get("cause", ""),
                row.get("requirement", ""),
                row.get("process_detail", ""),
            ]
        ),
        axis=1,
    )

    def score_text(text: str) -> int:
        score = 0
        for keyword in keyword_set:
            score += text.count(keyword)
        return score

    scores = pattern_texts.apply(score_text)
    filtered = filtered.assign(match_score=scores)
    filtered = filtered.sort_values(by=["match_score", "rpn"], ascending=[False, False])
    return filtered


def build_change_report(
    changes: list[ChangeRecord],
    pfmea_dataset: PfmeaDataset,
    *,
    bop_config: BopConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, PfmeaContext]]:
    """差分リストからPFMEAサマリーレポートとPFMEA参照データを生成する。"""
    if not changes:
        return pd.DataFrame(), {}

    conf = _ensure_config(bop_config)
    records = []
    pfmea_context: dict[str, PfmeaContext] = {}

    def _build_single(change: ChangeRecord) -> tuple[str, pd.DataFrame, dict[str, str]]:
        with time_block(
            "match_pfmea", metadata={"phase": "analysis", "change_id": change.change_id}
        ):
            matched = match_pfmea(change, pfmea_dataset, bop_config=conf)
        record = {
            "変更ID": change.change_id,
            "バリエーション": change.variant_id,
            "ブロック": change.block,
            "ステーション": change.station,
            "対象部品": change.part_label,
            "対象部品（流用元）": change.original_part_label or "",
            "対象部品（変更後）": change.updated_part_label or "",
            "変更種別": change.change_type,
            "旧品番": change.original_value,
            "新品番": change.new_value,
            "形状の特長": change.shape_feature or "",
            "データ品質警告": (
                "品番は同じですが部品名称が異なります。元データを確認してください。"
                if change.is_label_mismatch
                else ""
            ),
        }
        return change.change_id, matched, record

    worker_count = min(4, max(1, len(changes)))
    with time_block(
        "change_analysis.thread_pool",
        metadata={"phase": "analysis", "count": len(changes)},
    ):
        results = parallel_map(_build_single, changes, max_workers=worker_count)
        for change_id, matched, record in results:
            block_label = str(record.get("ブロック", ""))
            block_summaries = pfmea_dataset.process_summaries.get(block_label, {})
            pfmea_context[change_id] = PfmeaContext(
                data=matched,
                block=block_label or None,
                summaries=block_summaries,
            )
            records.append(record)

    with time_block(
        "change_analysis.report_frame",
        metadata={"phase": "analysis", "rows": len(records)},
    ):
        report_df = pd.DataFrame(records)
    return report_df, pfmea_context
