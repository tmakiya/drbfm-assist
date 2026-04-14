"""LLM リトライポリシー定義.

モジュール横断で一貫したリトライ戦略を適用するための統一定義。
LangChain の with_retry() メソッドと互換性のある形式で定義。

Usage:
    from src.services.llm_retry_policies import RetryPolicies, apply_retry_policy

    policy = RetryPolicies.CRITICAL
    model_with_retry = apply_retry_policy(model, policy)
    result = await model_with_retry.ainvoke(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import Runnable
from langchain_core.runnables.retry import ExponentialJitterParams


@dataclass(frozen=True)
class RetryPolicy:
    """LangChain with_retry() 互換のリトライポリシー.

    Attributes:
        stop_after_attempt: 最大試行回数
        initial: 初期遅延（秒）
        max: 最大遅延（秒）
        exp_base: 指数バックオフの底
        jitter: ジッタ（秒）
        retry_exceptions: リトライ対象の例外タイプ
    """

    stop_after_attempt: int = 3
    initial: float = 0.5
    max: float = 60.0
    exp_base: float = 2.0
    jitter: float = 0.1
    retry_exceptions: tuple[type[BaseException], ...] = field(
        default=(Exception,), hash=False
    )

    # Backward compatibility aliases
    @property
    def max_attempts(self) -> int:
        """Backward compatibility: max_attempts -> stop_after_attempt."""
        return self.stop_after_attempt

    @property
    def base_delay(self) -> float:
        """Backward compatibility: base_delay -> initial."""
        return self.initial

    @property
    def multiplier(self) -> float:
        """Backward compatibility: multiplier -> exp_base."""
        return self.exp_base

    def normalized_attempts(self) -> int:
        """Backward compatibility method."""
        return max(1, self.stop_after_attempt)

    def to_jitter_params(self) -> ExponentialJitterParams:
        """Convert to ExponentialJitterParams for with_retry()."""
        return {
            "initial": self.initial,
            "max": self.max,
            "exp_base": self.exp_base,
            "jitter": self.jitter,
        }


def apply_retry_policy(
    runnable: Runnable[Any, Any],
    policy: RetryPolicy,
) -> Runnable[Any, Any]:
    """Apply retry policy to a LangChain Runnable using with_retry().

    Args:
        runnable: LangChain Runnable instance (BaseChatModel, structured output, etc.)
        policy: RetryPolicy to apply

    Returns:
        Runnable with retry behavior applied
    """
    return runnable.with_retry(
        retry_if_exception_type=policy.retry_exceptions,
        wait_exponential_jitter=True,
        exponential_jitter_params=policy.to_jitter_params(),
        stop_after_attempt=policy.stop_after_attempt,
    )


class RetryPolicies:
    """リトライポリシーの集約.

    ユースケースに応じた最適なリトライ戦略を提供する。
    """

    # 標準的な LLM 呼び出し
    # PFMEA アセスメント、一般的なクエリ向け
    STANDARD = RetryPolicy(
        stop_after_attempt=3,
        initial=0.5,
        max=30.0,
        exp_base=2.0,
        jitter=0.1,
    )

    # 重要度の高い処理
    # 機能マッピングなど、失敗時の影響が大きい処理向け
    CRITICAL = RetryPolicy(
        stop_after_attempt=5,
        initial=1.0,
        max=60.0,
        exp_base=1.5,
        jitter=0.2,
    )

    # リスク評価用
    # 並列実行が多いため、競合を避けるために遅延を長めに設定
    RISK_RATING = RetryPolicy(
        stop_after_attempt=4,
        initial=0.8,
        max=45.0,
        exp_base=1.6,
        jitter=0.2,
    )

    # malformed レスポンスのリカバリー
    # JSON 解析失敗時の再試行用、遅延を長めに設定
    MALFORMED_RECOVERY = RetryPolicy(
        stop_after_attempt=2,
        initial=2.0,
        max=10.0,
        exp_base=1.0,
        jitter=0.5,
    )

    # レート制限対応
    # 429 エラー等が連続した場合の保守的なリトライ
    RATE_LIMITED = RetryPolicy(
        stop_after_attempt=5,
        initial=5.0,
        max=120.0,
        exp_base=2.0,
        jitter=1.0,
    )

    # 軽量処理用
    # 短いプロンプト、即座のレスポンスが期待される場合
    LIGHTWEIGHT = RetryPolicy(
        stop_after_attempt=2,
        initial=0.3,
        max=10.0,
        exp_base=1.5,
        jitter=0.1,
    )


# 定数としてもエクスポート（後方互換性のため）
STANDARD_RETRY_POLICY = RetryPolicies.STANDARD
CRITICAL_RETRY_POLICY = RetryPolicies.CRITICAL
RISK_RATING_RETRY_POLICY = RetryPolicies.RISK_RATING
MALFORMED_RECOVERY_RETRY_POLICY = RetryPolicies.MALFORMED_RECOVERY
RATE_LIMITED_RETRY_POLICY = RetryPolicies.RATE_LIMITED


__all__ = [
    "RetryPolicy",
    "RetryPolicies",
    "apply_retry_policy",
    "STANDARD_RETRY_POLICY",
    "CRITICAL_RETRY_POLICY",
    "RISK_RATING_RETRY_POLICY",
    "MALFORMED_RECOVERY_RETRY_POLICY",
    "RATE_LIMITED_RETRY_POLICY",
]
