from __future__ import annotations

from src.common.paths import PROJECT_ROOT

DEFAULT_RATINGS_PATH = PROJECT_ROOT / "config" / "pfmea_ratings.yaml"

PFMEA_COLUMN_MAP = {
    "requirement": 4,
    "failure_mode": 5,
    "effect": 6,
    "severity": 7,
    "priority_designation": 8,
    "cause": 9,
    "prevention": 10,
    "occurrence": 11,
    "detection_control": 12,
    "detection": 13,
    "rpn": 14,
    "recommended_action": 15,
    "process_sheet_reflection": 16,
    "responsible_owner": 17,
}

PROCESS_DETAIL_KEYWORDS = ("工程の機能", "製造保証項目")
IGNORE_TEXTBOX_KEYWORDS = ("品番一覧：",)

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_PACK = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_DRAWING_MAIN = "http://schemas.openxmlformats.org/drawingml/2006/main"

__all__ = [
    "DEFAULT_RATINGS_PATH",
    "IGNORE_TEXTBOX_KEYWORDS",
    "NS_DRAWING",
    "NS_DRAWING_MAIN",
    "NS_MAIN",
    "NS_REL_DOC",
    "NS_REL_PACK",
    "PFMEA_COLUMN_MAP",
    "PROCESS_DETAIL_KEYWORDS",
]
