from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.engine.decision import DecisionEngine


def test_decision_engine_without_vix_does_not_open_longs() -> None:
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
    assert {d.symbol for d in decisions} == {"AAA", "BBB"}
    # Sin VIX el régimen no está risk-on: no se abre largo.
    assert all(d.action in {"WATCH", "NO_TRADE"} for d in decisions)
    assert all(d.position_size == 0.0 for d in decisions)


def test_decision_engine_buys_when_risk_on_and_trend_up() -> None:
    s = AppSettings()
    s.universe.symbols = ["AAA"]
    s.universe.benchmark = "AAA"
    s.trading.direction = "long_only"
    s.risk.allowed_symbols = []
    s.risk.max_position_pct = 25.0
    s.risk.max_total_exposure_pct = 50.0
    s.resolve_paths()
    idx = pd.date_range("2022-01-01", periods=160, freq="B")
    close = pd.Series(100.0 + 0.4 * np.arange(len(idx)), index=idx).astype(float)
    px = pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 1000},
        index=idx,
    )
    vix_close = pd.Series(40.0 - 0.15 * np.arange(len(idx)), index=idx).astype(float)
    vix = pd.DataFrame(
        {
            "open": vix_close,
            "high": vix_close + 0.1,
            "low": vix_close - 0.1,
            "close": vix_close,
            "volume": 1000,
        },
        index=idx,
    )
    engine = DecisionEngine(s)
    decisions = engine.generate({"AAA": px, "^VIX": vix})
    by_sym = {d.symbol: d for d in decisions}
    assert by_sym["AAA"].action == "BUY"
    assert 0.0 < by_sym["AAA"].position_size <= 0.25
    assert by_sym["^VIX"].action != "BUY"

