from __future__ import annotations

from typing import Any

import streamlit as st

from src.ui import components as ui_components

from .constants import PFMEA_BLOCKS
from .module_loader import get_validation_module


def validate_uploaded_datasets(
    source_dataset: Any,
    target_dataset: Any,
    pfmea_dataset: Any,
    validation_module: Any = None,
) -> bool:
    validation_module = validation_module or get_validation_module()
    has_error = False
    if source_dataset is not None:
        source_issues = validation_module.validate_bop_dataset(source_dataset)
        has_error |= ui_components.render_validation_issues(
            "流用元編成表", source_issues
        )
    if target_dataset is not None:
        target_issues = validation_module.validate_bop_dataset(target_dataset)
        has_error |= ui_components.render_validation_issues(
            "変更後編成表", target_issues
        )
    if pfmea_dataset is not None:
        pfmea_issues = validation_module.validate_pfmea_bundle(
            pfmea_dataset, PFMEA_BLOCKS
        )
        has_error |= ui_components.render_validation_issues("PFMEAリスト", pfmea_issues)
    if has_error:
        st.info("エラーを解消した上で再度ファイルを読み込んでください。")
        return False
    return True


__all__ = ["validate_uploaded_datasets"]
