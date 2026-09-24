from __future__ import annotations

import pandas as pd
import pytest

from ibtrader.data.lineage import DataFrameWithMeta, DataLineage
from ibtrader.data.providers import DataQualityGate


def test_quality_gate_blocks_duplicates() -> None:
    idx = pd.to_datetime(["2024-01-01", "2024-01-01"])
    df = pd.DataFrame({"close": [1.0, 1.1]}, index=idx)
    meta = DataLineage(source="test")
    gate = DataQualityGate(min_rows=1)
    with pytest.raises(RuntimeError):
        gate.validate(DataFrameWithMeta(df, meta))

