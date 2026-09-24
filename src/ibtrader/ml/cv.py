from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Tuple

import numpy as np
import pandas as pd


@dataclass
class PurgedTimeSeriesSplit:
    """
    Simplified purged time series split with embargo.
    Splits index-ordered data into k folds, ensuring no lookahead.
    """

    n_splits: int = 5
    embargo: int = 5  # number of samples to embargo after each train end

    def split(self, X: pd.DataFrame) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        n = len(X)
        fold_size = n // self.n_splits
        indices = np.arange(n)
        for i in range(self.n_splits):
            test_start = i * fold_size
            test_end = (i + 1) * fold_size if i < self.n_splits - 1 else n
            embargo_end = min(n, test_start + self.embargo)
            train_idx = indices[: max(0, test_start - self.embargo)]
            if embargo_end < n:
                train_idx = np.concatenate([train_idx, indices[embargo_end:test_start]])
            test_idx = indices[test_start:test_end]
            yield train_idx, test_idx

