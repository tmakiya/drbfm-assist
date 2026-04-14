from __future__ import annotations

from src.common.bop import BopDataset
from src.ui.view_models import VariantOverviewViewModel


def build_variant_overview(
    source: BopDataset, target: BopDataset
) -> VariantOverviewViewModel:
    return VariantOverviewViewModel.from_datasets(source, target)


__all__ = ["build_variant_overview"]
