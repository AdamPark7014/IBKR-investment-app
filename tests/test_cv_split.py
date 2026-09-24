import numpy as np
import pandas as pd

from ibtrader.ml.cv import PurgedTimeSeriesSplit


def test_purged_time_series_split_no_leakage() -> None:
    X = pd.DataFrame({"x": np.arange(100)})
    splitter = PurgedTimeSeriesSplit(n_splits=5, embargo=5)
    for train_idx, test_idx in splitter.split(X):
        train_max = max(train_idx) if len(train_idx) > 0 else -1
        assert train_max < min(test_idx)  # no overlap
        # Embargo: ensure a gap between train end and test start
        if len(train_idx) > 0:
            assert (min(test_idx) - train_max) >= 5

