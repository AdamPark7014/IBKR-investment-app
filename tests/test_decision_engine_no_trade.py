from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.engine.decision import DecisionEngine


def test_decision_engine_produces_no_trade() -> None:
    s = AppSettings()
    s.universe.symbols = ["AAA", "BBB"]
    s.resolve_paths()
    idx = pd.date_range("2022-01-01", periods=120, freq="B")
    def frame(x0: float) -> pd.DataFrame:
        close = pd.Series(x0 + (0.1 * np.arange(len(idx))), index=idx).astype(float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000,
            },
            index=idx,
        )
    data = {"AAA": frame(100.0), "BBB": frame(200.0)}
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    assert all(d.action == "NO_TRADE" for d in decisions)
    assert {d.symbol for d in decisions} == {"AAA", "BBB"}

