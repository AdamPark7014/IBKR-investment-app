"""Build PBO diagnostic from an SMA param grid via purged fold Sharpes."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..config import AppSettings
from ..validation.signal import validate_sma_signal
from .pbo import pbo_from_fold_sharpe_rows
from .runner import SMA_GRID_CANDIDATES


def run_sma_grid_pbo(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    candidates: Sequence[Tuple[int, int]] | None = None,
    direction: str | None = None,
    n_splits: int = 6,
    embargo: int = 5,
) -> Dict[str, Any]:
    """CSCV-PBO over SMA (fast, slow) trials using purged CV fold Sharpes as periods."""
    grid = list(candidates) if candidates is not None else list(SMA_GRID_CANDIDATES)
    direction = direction or settings.trading.direction
    # Prefer even n_splits for CSCV halves
    if n_splits % 2 == 1:
        n_splits = n_splits + 1
    fold_rows: List[List[float]] = []
    labels: List[str] = []
    for fast, slow in grid:
        folds, _agg = validate_sma_signal(
            data=dict(data),
            symbol=symbol,
            fast=int(fast),
            slow=int(slow),
            direction=direction,
            n_splits=n_splits,
            embargo=int(embargo),
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
        )
        fold_rows.append([float(f.sharpe) for f in folds])
        labels.append(f"sma_{fast}_{slow}")
    pbo = pbo_from_fold_sharpe_rows(fold_rows)
    pbo["trial_ids"] = labels
    pbo["embargo"] = int(embargo)
    pbo["n_splits"] = int(n_splits)
    return pbo
