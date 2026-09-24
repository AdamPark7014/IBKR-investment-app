from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd


@dataclass
class LossMetrics:
    daily_loss_pct: float
    cumulative_loss_pct: float
    drawdown_from_peak_pct: float
    per_position_unrealized_pct: float
    realized_loss: float
    unrealized_loss: float


def compute_loss_metrics(
    equity_curve: pd.Series,
    day_start_equity: float,
    position_qty: int,
    avg_price: float,
    last_price: float,
    realized_pnl_cum: float,
) -> LossMetrics:
    equity_curve = equity_curve.dropna()
    current_equity = float(equity_curve.iloc[-1]) if len(equity_curve) else day_start_equity
    # Daily
    daily_loss_pct = 0.0 if day_start_equity == 0 else (current_equity - day_start_equity) / day_start_equity
    # Cumulative (vs first equity)
    first_equity = float(equity_curve.iloc[0]) if len(equity_curve) else day_start_equity
    cumulative_loss_pct = 0.0 if first_equity == 0 else (current_equity - first_equity) / first_equity
    # Drawdown from peak
    if len(equity_curve):
        peak = float(equity_curve.cummax().iloc[-1])
        drawdown_from_peak_pct = 0.0 if peak == 0 else (current_equity - peak) / peak
    else:
        drawdown_from_peak_pct = 0.0
    # Position unrealized
    unreal = 0.0
    if position_qty != 0 and avg_price > 0:
        if position_qty > 0:
            unreal = (last_price - avg_price) * position_qty
        else:
            unreal = (avg_price - last_price) * abs(position_qty)
    per_position_unrealized_pct = 0.0 if avg_price == 0 or position_qty == 0 else (last_price - avg_price) / avg_price * (1 if position_qty > 0 else -1)
    realized_loss = float(min(0.0, realized_pnl_cum))
    unrealized_loss = float(min(0.0, unreal))
    return LossMetrics(
        daily_loss_pct=float(daily_loss_pct),
        cumulative_loss_pct=float(cumulative_loss_pct),
        drawdown_from_peak_pct=float(drawdown_from_peak_pct),
        per_position_unrealized_pct=float(per_position_unrealized_pct),
        realized_loss=realized_loss,
        unrealized_loss=unrealized_loss,
    )

