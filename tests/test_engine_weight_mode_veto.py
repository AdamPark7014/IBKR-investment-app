"""Weight mode: a rebalance vetoed by the risk manager is proposed again on the next bars."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import AppSettings
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy

IDX = pd.bdate_range("2024-01-01", periods=40)


def _data() -> Dict[str, pd.DataFrame]:
    close = pd.Series(100.0, index=IDX)
    close.iloc[10:] = 80.0  # -20 % at the close of bar 10: with w = 0.3 the book loses ~6 % (> 5 % daily limit)
    open_ = close.shift(1).fillna(100.0)
    aaa = pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close), "close": close,
         "volume": 1e6},
        index=IDX,
    )
    bbb = pd.DataFrame({"open": 50.0, "high": 50.0, "low": 50.0, "close": 50.0, "volume": 1e6}, index=IDX)
    return {"AAA": aaa, "BBB": bbb}


class _RaiseOnLossDay(Strategy):
    signal_kind = "weight"

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        a = pd.Series(0.3, index=IDX)
        a.iloc[10:] = 0.6  # raised at the same close as the loss, then held constant (piecewise weights)
        return {"AAA": a, "BBB": pd.Series(0.0, index=IDX)}


def test_vetoed_weight_rebalance_is_retried(tmp_path: Path) -> None:
    data = _data()
    s = AppSettings()
    s.risk.killswitch_file = str(tmp_path / "KILL_SWITCH")
    res = backtest(
        data=data,
        strategy=_RaiseOnLossDay(),
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
        initial_equity=100_000.0,
        direction="long_only",
        risk_manager=RiskManager(s.risk, RiskState(starting_equity_today=100_000.0)),
        reg_fees_cfg=s.reg_fees,
    )
    pos = res.positions["AAA"]
    weight = pos * data["AAA"]["close"] / res.equity_curve
    # The day after the loss the daily-loss gate blocks the increase...
    assert abs(float(weight.iloc[11]) - 0.25) < 0.03
    # ...but the target is retried and reached once the gate clears (before: stuck at ~0.25 forever).
    assert abs(float(weight.iloc[-1]) - 0.6) < 0.02
    buys_after_loss = [t for t in res.trades if t[1] == "AAA" and pd.Timestamp(t[0]) > IDX[11] and int(t[2]) > 0]
    assert buys_after_loss, res.trades
