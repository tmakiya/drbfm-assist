"""LangChain ベースの LLM 呼び出しゲートウェイ。

with_retry() を使用したリトライ機構を提供。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

# Import RetryPolicy from llm_retry_policies for backward compatibility
from src.services.llm_retry_policies import RetryPolicy, apply_retry_policy


@dataclass
class LLMCallResult:
    status: Literal["success", "error"]
    content: str
    message: str = ""


# GenerationConfig stub for backward compatibility
GenerationConfig: Any = type("GenerationConfig", (), {})


def build_generation_config(**kwargs: Any) -> Any:
    """Build a generation config namespace from keyword arguments.

    Returns a SimpleNamespace that mimics the attribute interface.
    """
    return SimpleNamespace(**kwargs)


async def arun_generation(
    model: BaseChatModel,
    *,
    prompt: str,
    generation_config: Any = None,
    retry_policy: RetryPolicy | None = None,
    response_mime_type: str | None = None,
    response_schema: dict[str, Any] | None = None,
) -> LLMCallResult:
    """非同期版 LLM 呼び出し。LangChain の ainvoke() を使用する。

    Args:
        model: LangChain BaseChatModel インスタンス
        prompt: 入力プロンプト
        generation_config: 生成設定 (現在は未使用、互換性のため保持)
        retry_policy: リトライポリシー
        response_mime_type: レスポンスの MIME タイプ (JSON の場合 "application/json")
        response_schema: JSON スキーマ (structured output 用)

    Returns:
        LLMCallResult with status, content, and message
    """
    from src.services.llm_retry_policies import RetryPolicies

    policy = retry_policy or RetryPolicies.STANDARD

    try:
        # Structured output が必要な場合
        if response_schema is not None:
            structured_model = model.with_structured_output(response_schema)
            structured_with_retry = apply_retry_policy(structured_model, policy)
            result = await structured_with_retry.ainvoke([HumanMessage(content=prompt)])
            # Structured output の結果は dict なので JSON 文字列に変換
            if isinstance(result, dict):
                content = json.dumps(result, ensure_ascii=False)
            else:
                content = str(result)
        else:
            # 通常のテキスト生成（with_retry 適用）
            model_with_retry = apply_retry_policy(model, policy)
            response = await model_with_retry.ainvoke([HumanMessage(content=prompt)])
            raw_content = response.content
            if isinstance(raw_content, str):
                content = raw_content.strip()
            elif isinstance(raw_content, list):
                # content が list の場合 (マルチモーダル対応)
                text_parts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw_content
                ]
                content = "".join(text_parts).strip()
            else:
                content = str(raw_content).strip()

        if not content:
            return LLMCallResult(
                status="error",
                content="",
                message="AI推定結果を取得できませんでした。",
            )

        return LLMCallResult(status="success", content=content, message="")

    except Exception as exc:
        # with_retry() がリトライを使い果たした後の例外
        message = str(exc) or "AI推定結果を取得できませんでした。"
        return LLMCallResult(
            status="error",
            content="",
            message=f"{message}（{policy.stop_after_attempt}回試行）",
        )


__all__ = [
    "GenerationConfig",
    "LLMCallResult",
    "RetryPolicy",
    "arun_generation",
    "build_generation_config",
]
