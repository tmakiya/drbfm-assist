"""Streamlit非依存のセッション管理。CLI/サービス層から利用する軽量API。"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol


class RuntimeSessionProtocol(Protocol):
    """プロトコル: サービス層が必要とする最小限のセッションAPI。"""

    def get_vertex_models(self) -> dict[str, Any]: ...

    def get_vertex_model_info(self) -> dict[str, dict[str, str]]: ...

    def set_current_vertex_model(self, model_name: str) -> None: ...

    def get_current_vertex_model(self) -> str | None: ...

    def set_preferred_vertex_model(self, model_name: str) -> None: ...

    def get_preferred_vertex_model(self) -> str | None: ...

    def is_pfmea_mapping_ready(
        self, signature: str | None, model_name: str
    ) -> bool: ...

    def mark_pfmea_mapping_ready(
        self, signature: str | None, model_name: str
    ) -> None: ...

    def get_pfmea_mapping_cache(self) -> dict[str, dict[str, Any]]: ...

    def update_pfmea_mapping_cache(
        self, signature: str, entry: Mapping[str, Any]
    ) -> None: ...

    def set_pfmea_mapping_results(
        self, results: Mapping[str, Mapping[str, Any]]
    ) -> None: ...

    def get_pfmea_mapping_results(self) -> dict[str, Any]: ...

    def set_pfmea_mapping_logs(
        self, change_id: str, logs: Mapping[str, Any]
    ) -> None: ...

    def get_pfmea_mapping_logs(self) -> dict[str, Any]: ...


@dataclass
class RuntimeSession(RuntimeSessionProtocol):
    """辞書ベースの軽量セッション実装。"""

    storage: MutableMapping[str, Any]

    PFMEA_MAPPING_CACHE_KEY: str = "pfmea_function_mapping_cache"
    PFMEA_MAPPING_RESULTS_KEY: str = "pfmea_function_mapping_results"
    PFMEA_MAPPING_READY_KEY: str = "pfmea_function_mapping_ready"
    PFMEA_MAPPING_LOG_KEY: str = "pfmea_mapping_logs"
    VERTEX_MODELS_KEY: str = "vertex_models"
    VERTEX_MODEL_INFO_KEY: str = "vertex_model_info"
    VERTEX_MODEL_CURRENT_KEY: str = "vertex_model_current"
    VERTEX_MODEL_PREFERENCE_KEY: str = "vertex_model_preference"

    # Vertex model metadata -----------------------------------------------------
    def get_vertex_models(self) -> dict[str, Any]:
        result = self.storage.get(self.VERTEX_MODELS_KEY)
        if not isinstance(result, dict):
            result = {}
            self.storage[self.VERTEX_MODELS_KEY] = result
        return result

    def get_vertex_model_info(self) -> dict[str, dict[str, str]]:
        result = self.storage.get(self.VERTEX_MODEL_INFO_KEY)
        if not isinstance(result, dict):
            result = {}
            self.storage[self.VERTEX_MODEL_INFO_KEY] = result
        return result

    def set_current_vertex_model(self, model_name: str) -> None:
        self.storage[self.VERTEX_MODEL_CURRENT_KEY] = model_name

    def get_current_vertex_model(self) -> str | None:
        value = self.storage.get(self.VERTEX_MODEL_CURRENT_KEY)
        return str(value) if value is not None else None

    def set_preferred_vertex_model(self, model_name: str) -> None:
        self.storage[self.VERTEX_MODEL_PREFERENCE_KEY] = model_name

    def get_preferred_vertex_model(self) -> str | None:
        value = self.storage.get(self.VERTEX_MODEL_PREFERENCE_KEY)
        return str(value) if value is not None else None

    # PFMEA mapping cache -------------------------------------------------------
    def clear_pfmea_mapping_cache(self) -> None:
        self.storage.pop(self.PFMEA_MAPPING_CACHE_KEY, None)
        self.storage.pop(self.PFMEA_MAPPING_RESULTS_KEY, None)
        self.storage.pop(self.PFMEA_MAPPING_READY_KEY, None)
        self.storage.pop(self.PFMEA_MAPPING_LOG_KEY, None)

    def mark_pfmea_mapping_ready(self, signature: str | None, model_name: str) -> None:
        if not signature:
            return
        registry = self.storage.setdefault(self.PFMEA_MAPPING_READY_KEY, {})
        if isinstance(registry, dict):
            registry[str(signature)] = str(model_name)

    def is_pfmea_mapping_ready(self, signature: str | None, model_name: str) -> bool:
        if not signature:
            return False
        registry = self.storage.get(self.PFMEA_MAPPING_READY_KEY)
        if not isinstance(registry, Mapping):
            return False
        stored = registry.get(str(signature))
        return stored == str(model_name)

    def get_pfmea_mapping_cache(self) -> dict[str, dict[str, Any]]:
        cache = self.storage.setdefault(self.PFMEA_MAPPING_CACHE_KEY, {})
        if isinstance(cache, dict):
            return cache
        self.storage[self.PFMEA_MAPPING_CACHE_KEY] = {}
        return {}

    def update_pfmea_mapping_cache(
        self, signature: str, entry: Mapping[str, Any]
    ) -> None:
        cache = self.get_pfmea_mapping_cache()
        normalized_entry: dict[str, Any] = {}
        for key, value in entry.items():
            if isinstance(value, (list, dict)):
                normalized_entry[str(key)] = value
            elif value is None:
                normalized_entry[str(key)] = ""
            else:
                normalized_entry[str(key)] = str(value)
        cache[str(signature)] = normalized_entry

    def set_pfmea_mapping_results(
        self, results: Mapping[str, Mapping[str, Any]]
    ) -> None:
        normalized: dict[str, dict[str, Any]] = {}
        for change_id, processes in results.items():
            if not isinstance(processes, Mapping):
                continue
            process_payload: dict[str, Any] = {}
            for process_name, payload in processes.items():
                if not isinstance(payload, Mapping):
                    continue
                records = payload.get("records")
                normalized_records: list[dict[str, Any]] = []
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict):
                            normalized_records.append(dict(record))
                process_payload[str(process_name)] = {
                    "signature": str(payload.get("signature", "")),
                    "raw_text": str(payload.get("raw_text", "")),
                    "records": normalized_records,
                    "errors": list(map(str, payload.get("errors", []))),
                }
            if process_payload:
                normalized[str(change_id)] = process_payload
        self.storage[self.PFMEA_MAPPING_RESULTS_KEY] = normalized

    def get_pfmea_mapping_results(self) -> dict[str, Any]:
        payload = self.storage.get(self.PFMEA_MAPPING_RESULTS_KEY, {})
        if not isinstance(payload, dict):
            return {}
        normalized: dict[str, Any] = {}
        for change_id, processes in payload.items():
            if not isinstance(processes, Mapping):
                continue
            normalized[str(change_id)] = {}
            for process_name, record_payload in processes.items():
                if not isinstance(record_payload, Mapping):
                    continue
                records = record_payload.get("records", [])
                normalized_records: list[dict[str, Any]] = []
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict):
                            normalized_records.append(dict(record))
                normalized[str(change_id)][str(process_name)] = {
                    "signature": str(record_payload.get("signature", "")),
                    "raw_text": str(record_payload.get("raw_text", "")),
                    "records": normalized_records,
                    "errors": list(map(str, record_payload.get("errors", []))),
                }
        return normalized

    def set_pfmea_mapping_logs(self, change_id: str, logs: Mapping[str, Any]) -> None:
        registry = self.storage.setdefault(self.PFMEA_MAPPING_LOG_KEY, {})
        if not isinstance(registry, dict):
            registry = {}
            self.storage[self.PFMEA_MAPPING_LOG_KEY] = registry
        registry[str(change_id)] = dict(logs)

    def get_pfmea_mapping_logs(self) -> dict[str, Any]:
        payload = self.storage.get(self.PFMEA_MAPPING_LOG_KEY, {})
        return dict(payload) if isinstance(payload, dict) else {}


__all__ = ["RuntimeSession", "RuntimeSessionProtocol"]
