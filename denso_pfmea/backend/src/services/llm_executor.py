from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.common.perf import record_event
from src.services import llm_gateway
from src.services.llm_metrics import get_llm_metrics

_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "too many requests",
    "resource exhausted",
    "resourceexhausted",
    "quota",
    "429",
    "exceeded",
    "レート",
)


@dataclass(frozen=True)
class LLMExecutionMetadata:
    """メトリクス記録用の最低限の情報を保持する構造体。"""

    operation: str
    model_name: str | None = None
    extra: Mapping[str, Any] = None  # type: ignore[assignment]


class LLMExecutor:
    """LLM呼び出しの計測・ラップを行う軽量ユーティリティ。"""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        operation_name: str = "llm_call",
    ) -> None:
        self._model = model
        self._operation_name = operation_name

    @property
    def model(self) -> BaseChatModel:
        return self._model

    async def agenerate(
        self,
        prompt: str,
        *,
        generation_config: Any = None,
        retry_policy: llm_gateway.RetryPolicy | None = None,
        response_mime_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> llm_gateway.LLMCallResult:
        """非同期版 LLM 呼び出しを実行し、実行時間を計測して返す。"""
        start = time.perf_counter()
        result = await llm_gateway.arun_generation(
            self._model,
            prompt=prompt,
            generation_config=generation_config,
            retry_policy=retry_policy,
            response_mime_type=response_mime_type,
            response_schema=response_schema,
        )
        end = time.perf_counter()
        meta: dict[str, Any] = {
            "status": result.status,
            "mime": response_mime_type or "text",
        }
        if metadata:
            meta.update({str(key): value for key, value in metadata.items()})
        record_event(self._operation_name, start=start, end=end, metadata=meta)
        get_llm_metrics().record_call(
            self._operation_name,
            result.status,
            duration=end - start,
            metadata=meta,
        )
        return result

    @staticmethod
    def is_rate_limit_message(message: str) -> bool:
        lowered = message.lower()
        return any(keyword in lowered for keyword in _RATE_LIMIT_KEYWORDS)


__all__ = ["LLMExecutor", "LLMExecutionMetadata"]
