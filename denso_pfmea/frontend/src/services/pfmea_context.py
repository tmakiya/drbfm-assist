from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.common.pfmea.models import ProcessSummary


@dataclass(frozen=True)
class PfmeaContext:
    data: pd.DataFrame | None
    block: str | None = None
    summaries: Mapping[str, ProcessSummary] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        if self.data is None:
            raise AttributeError(name)
        return getattr(self.data, name)


__all__ = ["PfmeaContext"]
