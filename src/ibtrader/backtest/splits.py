from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import pandas as pd


@dataclass
class TimeSplits:
    train: Tuple[pd.Timestamp, pd.Timestamp]
    val: Tuple[pd.Timestamp, pd.Timestamp]
    test: Tuple[pd.Timestamp, pd.Timestamp]
    oos: Tuple[pd.Timestamp, pd.Timestamp]


def split_by_ratio(index: pd.DatetimeIndex, ratios=(0.6, 0.2, 0.2)) -> TimeSplits:
    n = len(index)
    r1, r2, r3 = ratios
    i1 = int(n * r1)
    i2 = i1 + int(n * r2)
    train = (index[0], index[i1 - 1])
    val = (index[i1], index[i2 - 1])
    test = (index[i2], index[-1])
    # OOS simple: la última porción independiente (aquí igual a test por simplicidad)
    oos = test
    return TimeSplits(train=train, val=val, test=test, oos=oos)

