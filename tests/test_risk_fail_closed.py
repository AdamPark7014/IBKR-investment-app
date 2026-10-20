from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        return {sym: pd.Series(1, index=df.index) for sym, df in data.items()}


def _sample_data() -> dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-01", periods=30, freq="B")
    prices = pd.DataFrame(
        {
            "open": 100.0 + np.arange(30),
            "high": 101.0 + np.arange(30),
            "low": 99.0 + np.arange(30),
            "close": 100.0 + np.arange(30),
            "volume": 1_000_000,
        },
        index=idx,
    )
    return {"SPY": prices}


def test_drawdown_check_failure_blocks_exposure_increase(monkeypatch) -> None:
    data = _sample_data()
    cfg = RiskConfig(killswitch_file="./data/NO_KILL", drawdown_limit_pct=10.0)
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))

    def _raise_drawdown(self, current_equity: float):
        raise RuntimeError("simulated drawdown check failure")

    monkeypatch.setattr(RiskManager, "check_drawdown", _raise_drawdown)

    result = backtest(
        data=data,
        strategy=AlwaysLong(),
        commission_cfg=CommissionConfig(),
        slippage_cfg=SlippageConfig(),
        initial_equity=100_000.0,
        risk_manager=rm,
    )

    assert result.stats.trade_count == 0
    assert int(result.positions["SPY"].abs().max()) == 0
    assert len(result.trades) == 0
