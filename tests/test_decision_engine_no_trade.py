from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ibtrader.config import AppSettings
from ibtrader.engine.decision import DecisionEngine
from ibtrader.risk.manager import RiskManager


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


def _risk_on_buy_frame() -> tuple[AppSettings, dict[str, pd.DataFrame]]:
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
    return s, {"AAA": px, "^VIX": vix}


def test_decision_engine_killswitch_file_yields_no_trade(tmp_path: Path) -> None:
    ks = tmp_path / "KILL_SWITCH"
    ks.write_text("1", encoding="utf-8")
    s, data = _risk_on_buy_frame()
    s.risk.killswitch_file = str(ks)
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    aaa = next(d for d in decisions if d.symbol == "AAA")
    assert aaa.action == "NO_TRADE"
    assert aaa.position_size == 0.0


def test_decision_engine_halted_before_generate_blocks_buy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s, data = _risk_on_buy_frame()
    real_init = RiskManager.__init__

    def _init_with_halt(self: RiskManager, cfg: object) -> None:
        real_init(self, cfg)
        self.state.halted = True
        self.fsm.set_restricted()

    monkeypatch.setattr(RiskManager, "__init__", _init_with_halt)
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    aaa = next(d for d in decisions if d.symbol == "AAA")
    assert aaa.action == "NO_TRADE"
    assert aaa.position_size == 0.0


def test_decision_engine_buys_when_risk_on_and_trend_up() -> None:
    s, data = _risk_on_buy_frame()
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    by_sym = {d.symbol: d for d in decisions}
    assert by_sym["AAA"].action == "BUY"
    assert 0.0 < by_sym["AAA"].position_size <= 0.25
    assert by_sym["^VIX"].action != "BUY"

