"""Multi-factor market analyzer scorecard (research / decision-support only).

Honest purpose
--------------
Rank names and regimes for *where not to lose first* and which symbols deserve
owner-PC research re-runs. This is **not** a promise of large profits, a
guaranteed edge, or a "hyper model that always wins."

Institutional layers (point-in-time, no look-ahead on the as-of bar):
1. Trend / time-series momentum
2. Cross-sectional relative strength
3. Volatility & drawdown risk
4. Breadth / risk-on proxy
5. Composite score → AVOID | WATCH | RESEARCH_CANDIDATE
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from ..intelligence.regime import compute_breadth


def _last_close(df: pd.DataFrame) -> Optional[float]:
    if df is None or df.empty or "close" not in df.columns:
        return None
    v = float(df["close"].astype(float).iloc[-1])
    return v if v == v else None


def _pct_change(close: pd.Series, lookback: int) -> float:
    if len(close) <= lookback:
        return float("nan")
    a = float(close.iloc[-1])
    b = float(close.iloc[-1 - lookback])
    if b == 0 or b != b or a != a:
        return float("nan")
    return (a / b) - 1.0


def _realized_vol(close: pd.Series, lookback: int = 21) -> float:
    if len(close) < lookback + 1:
        return float("nan")
    rets = close.pct_change().iloc[-lookback:]
    vol = float(rets.std(ddof=0))
    if vol != vol:
        return float("nan")
    import math

    return float(vol) * math.sqrt(252.0)


def _rolling_max_dd(close: pd.Series, lookback: int = 63) -> float:
    if len(close) < 5:
        return float("nan")
    window = close.iloc[-min(lookback, len(close)) :]
    dd = window / window.cummax() - 1.0
    return float(dd.min())


def _above_ma(close: pd.Series, window: int = 200) -> Optional[bool]:
    if len(close) < window:
        return None
    ma = float(close.rolling(window).mean().iloc[-1])
    px = float(close.iloc[-1])
    if ma != ma or px != px:
        return None
    return bool(px > ma)


def _clip01(x: float) -> float:
    if x != x:
        return 0.0
    return float(min(max(x, 0.0), 1.0))


def score_symbol(
    close: pd.Series,
    *,
    rs_percentile: float,
) -> Dict[str, Any]:
    """Score one name into sub-scores in [0, 1] and a composite."""
    mom21 = _pct_change(close, 21)
    mom63 = _pct_change(close, 63)
    mom126 = _pct_change(close, 126)
    vol = _realized_vol(close, 21)
    mdd = _rolling_max_dd(close, 63)
    above200 = _above_ma(close, 200)
    above50 = _above_ma(close, 50)

    # Trend: positive medium-horizon mom + above MAs
    trend_raw = 0.0
    for m, w in ((mom21, 0.25), (mom63, 0.4), (mom126, 0.35)):
        if m == m:
            trend_raw += w * _clip01(0.5 + m / 0.2)  # ~±20% maps around mid
    if above50 is True:
        trend_raw = min(1.0, trend_raw + 0.1)
    if above200 is True:
        trend_raw = min(1.0, trend_raw + 0.15)
    if above200 is False:
        trend_raw = max(0.0, trend_raw - 0.25)

    # Risk: lower vol and milder DD → higher score (loss-mitigation friendly)
    # Target retail-ish vol ~15%; DD worse than -15% over 63d is harsh.
    vol_score = 1.0 - _clip01((vol if vol == vol else 0.3) / 0.40)
    dd_score = 1.0 - _clip01(abs(mdd if mdd == mdd else -0.2) / 0.25)
    risk_score = 0.55 * vol_score + 0.45 * dd_score

    rs_score = _clip01(float(rs_percentile))

    # Composite weights: loss-mitigation tilts toward risk + trend confirmation
    composite = 0.35 * trend_raw + 0.30 * rs_score + 0.35 * risk_score

    action = "AVOID"
    if composite >= 0.62 and above200 is not False and rs_score >= 0.55:
        action = "RESEARCH_CANDIDATE"
    elif composite >= 0.45:
        action = "WATCH"

    risk_flags: List[str] = []
    if above200 is False:
        risk_flags.append("below_sma200")
    if mdd == mdd and mdd < -0.15:
        risk_flags.append("deep_63d_drawdown")
    if vol == vol and vol > 0.35:
        risk_flags.append("high_realized_vol")
    if rs_score < 0.35:
        risk_flags.append("weak_relative_strength")
    if risk_flags and action == "RESEARCH_CANDIDATE":
        action = "WATCH"  # never promote when hard risk flags fire

    return {
        "mom_21": mom21 if mom21 == mom21 else None,
        "mom_63": mom63 if mom63 == mom63 else None,
        "mom_126": mom126 if mom126 == mom126 else None,
        "vol_21_ann": vol if vol == vol else None,
        "max_dd_63": mdd if mdd == mdd else None,
        "above_sma50": above50,
        "above_sma200": above200,
        "rs_percentile": rs_score,
        "scores": {
            "trend": round(trend_raw, 4),
            "relative_strength": round(rs_score, 4),
            "risk_quality": round(risk_score, 4),
            "composite": round(composite, 4),
        },
        "action": action,
        "risk_flags": risk_flags,
    }


def analyze_market(
    data: Mapping[str, pd.DataFrame],
    *,
    symbols: Sequence[str] | None = None,
    benchmark: str = "SPY",
) -> Dict[str, Any]:
    """Build a cross-sectional + regime scorecard for the loaded universe."""
    syms = [s for s in (list(symbols) if symbols is not None else list(data.keys())) if s in data]
    # Relative strength: rank by 63d return
    mom63_map: Dict[str, float] = {}
    for sym in syms:
        close = data[sym]["close"].astype(float)
        m = _pct_change(close, 63)
        if m == m:
            mom63_map[sym] = m
    if mom63_map:
        ordered = sorted(mom63_map.values())

        def _pctile(v: float) -> float:
            # empirical CDF percentile in [0,1]
            return float(sum(1 for x in ordered if x <= v) / len(ordered))

        rs = {s: _pctile(v) for s, v in mom63_map.items()}
    else:
        rs = {s: 0.5 for s in syms}

    rows: List[Dict[str, Any]] = []
    for sym in syms:
        close = data[sym]["close"].astype(float)
        scored = score_symbol(close, rs_percentile=rs.get(sym, 0.5))
        scored["symbol"] = sym
        scored["last_close"] = _last_close(data[sym])
        rows.append(scored)

    rows.sort(key=lambda r: float((r.get("scores") or {}).get("composite") or 0.0), reverse=True)

    # Universe regime
    breadth = float("nan")
    try:
        b = compute_breadth(dict(data), long_ma=200)
        if len(b):
            breadth = float(b.iloc[-1])
    except Exception:
        breadth = float("nan")

    bench_trend = None
    if benchmark in data:
        bench_trend = _above_ma(data[benchmark]["close"].astype(float), 200)

    risk_on_proxy = bool((breadth == breadth and breadth >= 0.55) and (bench_trend is not False))
    cash_bias = not risk_on_proxy

    n_avoid = sum(1 for r in rows if r["action"] == "AVOID")
    n_watch = sum(1 for r in rows if r["action"] == "WATCH")
    n_cand = sum(1 for r in rows if r["action"] == "RESEARCH_CANDIDATE")

    return {
        "benchmark": benchmark,
        "n_symbols": len(rows),
        "regime": {
            "breadth_above_sma200": breadth if breadth == breadth else None,
            "benchmark_above_sma200": bench_trend,
            "risk_on_proxy": risk_on_proxy,
            "cash_bias": cash_bias,
        },
        "action_counts": {"AVOID": n_avoid, "WATCH": n_watch, "RESEARCH_CANDIDATE": n_cand},
        "ranked": rows,
        "top_research": [r["symbol"] for r in rows if r["action"] == "RESEARCH_CANDIDATE"][:5],
        "avoid": [r["symbol"] for r in rows if r["action"] == "AVOID"],
        "disclaimer": (
            "Scorecard is loss-mitigation / research triage — NOT a buy list, "
            "NOT a guarantee of profit, NOT 'almost never lose'. "
            "RESEARCH_CANDIDATE only means worth walk-forward re-run on owner-PC."
        ),
    }
