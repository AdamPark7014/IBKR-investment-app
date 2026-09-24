from __future__ import annotations

import pandas as pd

from ibtrader.data.validators import validate_timeseries_strict


def test_validate_timeseries_detects_issues() -> None:
    idx_dup = pd.to_datetime(["2020-01-01", "2020-01-01"])
    df_dup = pd.DataFrame({"close": [1, 2]}, index=idx_dup)
    ok, _ = validate_timeseries_strict(df_dup)
    assert not ok

    idx_desc = pd.to_datetime(["2020-01-02", "2020-01-01"])
    df_desc = pd.DataFrame({"close": [2, 1]}, index=idx_desc)
    ok, _ = validate_timeseries_strict(df_desc)
    assert not ok

    idx_ok = pd.date_range("2020-01-01", periods=3, freq="B")
    df_ok = pd.DataFrame({"close": [1, 2, 3]}, index=idx_ok)
    ok, _ = validate_timeseries_strict(df_ok)
    assert ok

