from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

DISCLAIMER = "Triage only. Not a buy list. Not predictive of returns."


def _close_col(df: pd.DataFrame) -> pd.Series:
    if "close" in df.columns:
        return df["close"].astype(float)
    return df.iloc[:, 0].astype(float)


def _slice(
    prices: Dict[str, pd.DataFrame], symbol: str, as_of: pd.Timestamp
) -> Optional[pd.Series]:
    df = prices.get(symbol)
    if df is None or len(df) == 0:
        return None
    s = _close_col(df).copy()
    s.index = pd.to_datetime(s.index)
    out = s.loc[s.index <= as_of].dropna()
    return out if len(out) else None


def _pick(prices: Dict[str, pd.DataFrame], *cands: str) -> Optional[str]:
    keys = {k.upper(): k for k in prices}
    for c in cands:
        if c.upper() in keys:
            return keys[c.upper()]
    return None


def _ann_vol20(close: pd.Series) -> Optional[float]:
    if len(close) < 3:
        return None
    rets = close.pct_change().dropna().tail(20)
    if len(rets) < 2:
        return None
    return float(rets.std(ddof=0) * np.sqrt(252))


def build_market_radar(
    prices: Dict[str, pd.DataFrame],
    *,
    as_of: Optional[pd.Timestamp] = None,
) -> Dict[str, Any]:
    """Point-in-time market triage snapshot. Not alpha. Bars <= as_of only."""
    notes: list[str] = []
    empty: Dict[str, Any] = {
        "as_of": None,
        "equity_symbol": None,
        "equity_trend": None,
        "equity_vol_20": None,
        "risk_on_proxy": None,
        "rates_slope": None,
        "commodity_momentum": None,
        "breadth_proxy": None,
        "notes": notes,
        "disclaimer": DISCLAIMER,
    }
    if not prices:
        notes.append("empty prices")
        return empty

    if as_of is None:
        lasts = [pd.to_datetime(df.index).max() for df in prices.values() if len(df)]
        as_of = max(lasts) if lasts else None
    if as_of is None:
        notes.append("no dates")
        return empty
    as_of = pd.Timestamp(as_of)

    eq_sym = _pick(prices, "SPY") or next(iter(prices))
    if _pick(prices, "SPY") is None:
        notes.append(f"equity proxy={eq_sym}")
    eq = _slice(prices, eq_sym, as_of)

    equity_trend = None
    equity_vol_20 = None
    if eq is not None and len(eq) >= 100:
        ma100 = float(eq.tail(100).mean())
        last = float(eq.iloc[-1])
        band = 0.002
        if last > ma100 * (1 + band):
            equity_trend = 1
        elif last < ma100 * (1 - band):
            equity_trend = -1
        else:
            equity_trend = 0
        equity_vol_20 = _ann_vol20(eq)
    elif eq is not None:
        notes.append("equity bars < 100")
        equity_vol_20 = _ann_vol20(eq)

    risk_on_proxy = None
    vix_sym = _pick(prices, "^VIX", "VIX")
    if vix_sym:
        vx = _slice(prices, vix_sym, as_of)
        if vx is not None and len(vx) >= 50:
            risk_on_proxy = 1 if float(vx.iloc[-1]) < float(vx.tail(50).mean()) else 0
        else:
            notes.append("VIX short history")
    else:
        notes.append("no VIX")

    rates_slope = None
    tlt, ief = _pick(prices, "TLT"), _pick(prices, "IEF")
    if tlt and ief:
        a, b = _slice(prices, tlt, as_of), _slice(prices, ief, as_of)
        if a is not None and b is not None and len(a) >= 21 and len(b) >= 21:
            rates_slope = float(a.iloc[-1] / a.iloc[-21] - 1.0) - float(
                b.iloc[-1] / b.iloc[-21] - 1.0
            )
    else:
        notes.append("no TLT/IEF")

    commodity_momentum = None
    cmd = _pick(prices, "GLD", "PDBC")
    if cmd:
        c = _slice(prices, cmd, as_of)
        if c is not None and len(c) >= 61:
            commodity_momentum = float(c.iloc[-1] / c.iloc[-61] - 1.0)
    else:
        notes.append("no GLD/PDBC")

    above = tot = 0
    for sym in prices:
        s = _slice(prices, sym, as_of)
        if s is None or len(s) < 50:
            continue
        tot += 1
        if float(s.iloc[-1]) > float(s.tail(50).mean()):
            above += 1
    breadth_proxy = (above / tot) if tot else None

    return {
        "as_of": as_of.date().isoformat(),
        "equity_symbol": eq_sym,
        "equity_trend": equity_trend,
        "equity_vol_20": equity_vol_20,
        "risk_on_proxy": risk_on_proxy,
        "rates_slope": rates_slope,
        "commodity_momentum": commodity_momentum,
        "breadth_proxy": breadth_proxy,
        "notes": notes,
        "disclaimer": DISCLAIMER,
    }


__all__ = ["build_market_radar", "DISCLAIMER"]
