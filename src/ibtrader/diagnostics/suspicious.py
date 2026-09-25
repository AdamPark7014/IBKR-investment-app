from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np
import pandas as pd

from ..backtest.engine import BacktestResult


@dataclass
class Suspicion:
    code: str
    reason: str


def _has_future_dates(df: pd.DataFrame) -> bool:
    try:
        max_dt = pd.to_datetime(df.index.max())
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        return bool(max_dt > today)
    except Exception:
        return False


def diagnose(
    result: BacktestResult,
    datasets: Dict[str, pd.DataFrame],
    lineage_sources: Dict[str, str] | None = None,
) -> List[Suspicion]:
    flags: List[Suspicion] = []
    stats = result.stats
    # Extreme performance
    if stats.cagr > 1.0:
        flags.append(Suspicion("extreme_cagr", f"CAGR>100% ({stats.cagr:.4f})"))
    if stats.sharpe > 3.0:
        flags.append(Suspicion("extreme_sharpe", f"Sharpe>3 ({stats.sharpe:.2f})"))
    # Trades but no costs
    if stats.trade_count > 0 and (stats.total_commission <= 0.0):
        flags.append(Suspicion("zero_costs", "Operó con comisiones totales = 0"))
    # Future dates in dataset
    for sym, df in datasets.items():
        if _has_future_dates(df):
            flags.append(Suspicion("future_dates", f"Datos de {sym} contienen fechas futuras"))
    # Equity discontinuity / impossible returns
    if len(result.returns.dropna()) > 0:
        max_abs = float(np.abs(result.returns.dropna()).max())
        if max_abs > 0.2:
            flags.append(Suspicion("large_step", f"Rendimiento diario extremo {max_abs:.2%}"))
    # Synthetic or mock sources
    if lineage_sources:
        for sym, src in lineage_sources.items():
            if str(src).lower() in {"fixture", "mock", "yahoo-mock"}:
                flags.append(Suspicion("synthetic_source", f"Fuente sintética para {sym}: {src}"))
    # Anomalous turnover (very high given band 0)
    if stats.turnover > 20.0:
        flags.append(Suspicion("anomalous_turnover", f"Turnover acumulado inusualmente alto: {stats.turnover:.2f}x"))
    # Too few trades on long period
    if len(result.equity_curve) >= 500 and stats.trade_count < 2:
        flags.append(Suspicion("too_few_trades", "Muy pocas operaciones en un horizonte amplio"))
    # Fill at signal price (naive heuristic): if any trade price equals previous day's close exactly
    for sym, df in datasets.items():
        closes = df["close"].astype(float)
        for d, s, q, p, _reason in result.trades:
            if s != sym:
                continue
            ts = pd.Timestamp(d)
            prev = closes.shift(1).reindex([ts]).iloc[0] if ts in closes.index else np.nan
            if np.isfinite(prev) and abs(float(prev) - float(p)) < 1e-9:
                flags.append(
                    Suspicion(
                        "fill_at_signal_price",
                        f"Llenado al precio de cierre previo en {sym} @ {ts.date()}",
                    )
                )
                break
    return flags

