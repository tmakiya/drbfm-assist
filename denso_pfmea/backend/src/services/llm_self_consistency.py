"""Self-Consistency 実装.

複数の推論パスをサンプリングし、最も一貫性のある回答を選択する手法。
重要な判断（自信度評価、判断の確定）で精度向上が期待できる。

Reference:
    - Self-Consistency Improves Chain of Thought Reasoning (ArXiv 2203.11171)
    - GSM8K: +17.9%, AQuA: +12.2% の精度向上実績

Usage:
    from src.services.llm_self_consistency import generate_with_self_consistency

    result = generate_with_self_consistency(
        runner=runner,
        prompt=prompt,
        n_samples=3,
        aggregation_fields=["判断", "自信度"],
    )

Note:
    - リクエスト数が n_samples 倍になるため、重要なケースのみに適用
    - 並列実行には executor の設定が必要
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SelfConsistencyResult:
    """Self-Consistency の結果."""

    # 最終的な集約結果
    aggregated: dict[str, Any]

    # 各サンプルの生データ
    samples: list[dict[str, Any]]

    # 集約に使用したフィールドごとの投票結果
    votes: dict[str, dict[str, int]]

    # サンプル数
    n_samples: int

    # 一致度（0-1、1が完全一致）
    consistency_score: float


def aggregate_by_majority_vote(
    samples: Sequence[dict[str, Any]],
    fields: Sequence[str],
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """多数決で各フィールドの最頻値を決定.

    Args:
        samples: 各サンプルの辞書リスト
        fields: 集約対象のフィールド名リスト

    Returns:
        (集約結果, フィールドごとの投票結果)
    """
    if not samples:
        return {}, {}

    aggregated = dict(samples[0])  # ベースとしてコピー
    votes: dict[str, dict[str, int]] = {}

    for field in fields:
        values = [str(s.get(field, "")) for s in samples if field in s]
        if not values:
            continue

        counter = Counter(values)
        votes[field] = dict(counter)

        # 最頻値を選択
        most_common_value, _ = counter.most_common(1)[0]

        # 数値フィールドの場合は型を維持
        original_value = samples[0].get(field)
        if isinstance(original_value, int):
            try:
                aggregated[field] = int(most_common_value)
            except ValueError:
                aggregated[field] = most_common_value
        elif isinstance(original_value, float):
            try:
                aggregated[field] = float(most_common_value)
            except ValueError:
                aggregated[field] = most_common_value
        else:
            aggregated[field] = most_common_value

    return aggregated, votes


def calculate_consistency_score(votes: Mapping[str, dict[str, int]]) -> float:
    """一致度スコアを計算.

    各フィールドの最頻値の割合の平均を返す。
    1.0 = 全サンプルが同じ値、0.5 = 半数が異なる値
    """
    if not votes:
        return 1.0

    scores = []
    for field_votes in votes.values():
        if not field_votes:
            continue
        total = sum(field_votes.values())
        if total == 0:
            continue
        max_count = max(field_votes.values())
        scores.append(max_count / total)

    return sum(scores) / len(scores) if scores else 1.0


def generate_with_self_consistency(
    generator: Callable[[], dict[str, Any]],
    *,
    n_samples: int = 3,
    aggregation_fields: Sequence[str] | None = None,
    min_consistency: float = 0.0,
) -> SelfConsistencyResult:
    """Self-Consistency を適用して複数サンプルから集約結果を生成.

    Args:
        generator: 単一サンプルを生成する関数（引数なし、dict を返す）
        n_samples: サンプル数（デフォルト: 3）
        aggregation_fields: 集約対象のフィールド名（デフォルト: ["判断", "自信度"]）
        min_consistency: 最低一致度（これ未満の場合は警告ログ）

    Returns:
        SelfConsistencyResult

    Note:
        generator は同期関数として呼び出される。
        非同期実行が必要な場合は呼び出し元で対応すること。

    Example:
        >>> def make_sample():
        ...     return runner.generate(prompt=prompt, ...)
        >>> result = generate_with_self_consistency(
        ...     generator=make_sample,
        ...     n_samples=3,
        ...     aggregation_fields=["判断", "自信度"],
        ... )
        >>> print(result.aggregated["判断"])
    """
    if n_samples < 1:
        n_samples = 1

    fields = list(aggregation_fields) if aggregation_fields else ["判断", "自信度"]

    # サンプル生成
    samples: list[dict[str, Any]] = []
    for i in range(n_samples):
        try:
            sample = generator()
            if isinstance(sample, dict):
                samples.append(sample)
            else:
                # Defensive: runtime may violate type hints
                logger.warning(
                    "Self-consistency sample %d returned non-dict: %s",
                    i,
                    type(sample).__name__,
                )
        except Exception as exc:
            logger.warning("Self-consistency sample %d failed: %s", i, exc)

    if not samples:
        logger.error("Self-consistency: all samples failed")
        return SelfConsistencyResult(
            aggregated={},
            samples=[],
            votes={},
            n_samples=n_samples,
            consistency_score=0.0,
        )

    # 集約
    aggregated, votes = aggregate_by_majority_vote(samples, fields)
    consistency_score = calculate_consistency_score(votes)

    if consistency_score < min_consistency:
        logger.warning(
            "Self-consistency score %.2f is below threshold %.2f",
            consistency_score,
            min_consistency,
        )

    logger.debug(
        "Self-consistency completed: n_samples=%d, consistency=%.2f, votes=%s",
        len(samples),
        consistency_score,
        votes,
    )

    return SelfConsistencyResult(
        aggregated=aggregated,
        samples=samples,
        votes=votes,
        n_samples=len(samples),
        consistency_score=consistency_score,
    )


__all__ = [
    "SelfConsistencyResult",
    "aggregate_by_majority_vote",
    "calculate_consistency_score",
    "generate_with_self_consistency",
]
