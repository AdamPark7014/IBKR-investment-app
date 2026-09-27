"""Multi-engine market analyzer (research triage — not a profit promise).

Engines (point-in-time, no look-ahead on the as-of bar):
1. Trend / TS momentum stack
2. Cross-sectional relative strength
3. Risk quality (vol + path DD)
4. Mean-reversion pressure (z vs MA)
5. Momentum quality (hit-rate consistency)
6. Volume thrust (if volume present)
7. Benchmark coupling (rolling corr)
8. Ensemble + disagreement → confidence

Actions remain AVOID | WATCH | RESEARCH_CANDIDATE.
Complexity here is *process power*, not a claim of mega returns.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

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


def _zscore_vs_ma(close: pd.Series, window: int = 20) -> float:
    if len(close) < window + 2:
        return float("nan")
    ma = close.rolling(window).mean()
    sd = close.rolling(window).std(ddof=0)
    m = float(ma.iloc[-1])
    s = float(sd.iloc[-1])
    px = float(close.iloc[-1])
    if s != s or s <= 1e-12 or m != m:
        return float("nan")
    return (px - m) / s


def _momentum_hit_rate(close: pd.Series, lookback: int = 63) -> float:
    if len(close) < lookback + 1:
        return float("nan")
    rets = close.pct_change().iloc[-lookback:]
    rets = rets.dropna()
    if len(rets) < 10:
        return float("nan")
    return float((rets > 0).mean())


def _volume_thrust(df: pd.DataFrame, lookback: int = 21) -> float:
    if "volume" not in df.columns or len(df) < lookback * 2:
        return float("nan")
    vol = df["volume"].astype(float)
    recent = float(vol.iloc[-lookback:].mean())
    prior = float(vol.iloc[-2 * lookback : -lookback].mean())
    if prior <= 0 or prior != prior or recent != recent:
        return float("nan")
    # Map ratio ~0.5..2.0 → 0..1 centered at 1.0
    ratio = recent / prior
    return _clip01(0.5 + (ratio - 1.0))


def _corr_to_bench(close: pd.Series, bench: pd.Series, lookback: int = 63) -> float:
    if len(close) < lookback + 2 or len(bench) < lookback + 2:
        return float("nan")
    a = close.pct_change().iloc[-lookback:]
    b = bench.reindex(close.index).pct_change().iloc[-lookback:]
    paired = pd.concat([a, b], axis=1).dropna()
    if len(paired) < 20:
        return float("nan")
    c = float(paired.iloc[:, 0].corr(paired.iloc[:, 1]))
    return c if c == c else float("nan")


def _engine_trend(close: pd.Series) -> Tuple[float, Dict[str, Any]]:
    mom21 = _pct_change(close, 21)
    mom63 = _pct_change(close, 63)
    mom126 = _pct_change(close, 126)
    above200 = _above_ma(close, 200)
    above50 = _above_ma(close, 50)
    raw = 0.0
    for m, w in ((mom21, 0.25), (mom63, 0.4), (mom126, 0.35)):
        if m == m:
            raw += w * _clip01(0.5 + m / 0.2)
    if above50 is True:
        raw = min(1.0, raw + 0.1)
    if above200 is True:
        raw = min(1.0, raw + 0.15)
    if above200 is False:
        raw = max(0.0, raw - 0.25)
    return float(raw), {
        "mom_21": mom21 if mom21 == mom21 else None,
        "mom_63": mom63 if mom63 == mom63 else None,
        "mom_126": mom126 if mom126 == mom126 else None,
        "above_sma50": above50,
        "above_sma200": above200,
    }


def _engine_risk(close: pd.Series) -> Tuple[float, Dict[str, Any]]:
    vol = _realized_vol(close, 21)
    mdd = _rolling_max_dd(close, 63)
    vol_score = 1.0 - _clip01((vol if vol == vol else 0.3) / 0.40)
    dd_score = 1.0 - _clip01(abs(mdd if mdd == mdd else -0.2) / 0.25)
    score = 0.55 * vol_score + 0.45 * dd_score
    return float(score), {
        "vol_21_ann": vol if vol == vol else None,
        "max_dd_63": mdd if mdd == mdd else None,
    }


def _engine_mean_rev(close: pd.Series) -> Tuple[float, Dict[str, Any]]:
    """High score = stretched and likely mean-reverting pressure (research only)."""
    z = _zscore_vs_ma(close, 20)
    if z != z:
        return 0.5, {"z_ma20": None}
    # Extreme |z| → higher MR pressure; mild z → mid
    pressure = _clip01(abs(z) / 2.5)
    return float(pressure), {"z_ma20": float(z)}


def _engine_mom_quality(close: pd.Series) -> Tuple[float, Dict[str, Any]]:
    hit = _momentum_hit_rate(close, 63)
    if hit != hit:
        return 0.5, {"hit_rate_63": None}
    # Prefer consistency mildly above coin-flip without requiring perfection
    score = _clip01((hit - 0.35) / 0.30)
    return float(score), {"hit_rate_63": float(hit)}


def score_symbol(
    close: pd.Series,
    *,
    rs_percentile: float,
    df: pd.DataFrame | None = None,
    bench_close: pd.Series | None = None,
) -> Dict[str, Any]:
    """Run the full engine stack and ensemble for one symbol."""
    trend_s, trend_meta = _engine_trend(close)
    risk_s, risk_meta = _engine_risk(close)
    mr_s, mr_meta = _engine_mean_rev(close)
    mq_s, mq_meta = _engine_mom_quality(close)
    rs_score = _clip01(float(rs_percentile))

    vol_thrust = _volume_thrust(df) if df is not None else float("nan")
    vol_s = _clip01(vol_thrust) if vol_thrust == vol_thrust else 0.5

    corr = (
        _corr_to_bench(close, bench_close, 63)
        if bench_close is not None
        else float("nan")
    )
    # Diversifier bonus when corr is low but trend/RS still ok — score mid for very high corr
    if corr == corr:
        corr_s = _clip01(1.0 - abs(corr) * 0.35)  # perfect corr slightly penalized
    else:
        corr_s = 0.5

    engines = {
        "trend": round(trend_s, 4),
        "relative_strength": round(rs_score, 4),
        "risk_quality": round(risk_s, 4),
        "mean_reversion_pressure": round(mr_s, 4),
        "momentum_quality": round(mq_s, 4),
        "volume_thrust": round(vol_s, 4),
        "bench_decoupling": round(corr_s, 4),
    }
    # Ensemble weights — loss-mitigation tilts risk + trend + RS
    weights = {
        "trend": 0.22,
        "relative_strength": 0.18,
        "risk_quality": 0.22,
        "mean_reversion_pressure": 0.08,  # informational; not a buy signal alone
        "momentum_quality": 0.14,
        "volume_thrust": 0.08,
        "bench_decoupling": 0.08,
    }
    composite = sum(engines[k] * weights[k] for k in weights)
    vals = list(engines.values())
    disagree = float(pd.Series(vals).std(ddof=0)) if vals else 0.0
    confidence = _clip01(1.0 - disagree * 2.2)

    above200 = trend_meta.get("above_sma200")
    mdd = risk_meta.get("max_dd_63")
    vol = risk_meta.get("vol_21_ann")

    action = "AVOID"
    if (
        composite >= 0.62
        and confidence >= 0.45
        and above200 is not False
        and rs_score >= 0.55
        and risk_s >= 0.40
    ):
        action = "RESEARCH_CANDIDATE"
    elif composite >= 0.45:
        action = "WATCH"

    risk_flags: List[str] = []
    if above200 is False:
        risk_flags.append("below_sma200")
    if mdd is not None and mdd < -0.15:
        risk_flags.append("deep_63d_drawdown")
    if vol is not None and vol > 0.35:
        risk_flags.append("high_realized_vol")
    if rs_score < 0.35:
        risk_flags.append("weak_relative_strength")
    if disagree > 0.28:
        risk_flags.append("engine_disagreement")
    if confidence < 0.35:
        risk_flags.append("low_ensemble_confidence")
    if risk_flags and action == "RESEARCH_CANDIDATE":
        action = "WATCH"

    return {
        **trend_meta,
        **risk_meta,
        **mr_meta,
        **mq_meta,
        "rs_percentile": rs_score,
        "corr_to_bench_63": corr if corr == corr else None,
        "engines": engines,
        "engine_weights": weights,
        "scores": {
            "trend": engines["trend"],
            "relative_strength": engines["relative_strength"],
            "risk_quality": engines["risk_quality"],
            "composite": round(float(composite), 4),
            "confidence": round(float(confidence), 4),
            "disagreement": round(float(disagree), 4),
        },
        "action": action,
        "risk_flags": risk_flags,
    }


def _sleeve_hypothesis(
    rows: Sequence[Mapping[str, Any]],
    *,
    cash_bias: bool,
) -> Dict[str, Any]:
    """Research allocation hypothesis — not advice, not a promise of gain."""
    n = len(rows)
    n_cand = sum(1 for r in rows if r.get("action") == "RESEARCH_CANDIDATE")
    n_avoid = sum(1 for r in rows if r.get("action") == "AVOID")
    if cash_bias or n == 0:
        cash, core, satellite = 0.55, 0.35, 0.10
    elif n_cand == 0:
        cash, core, satellite = 0.40, 0.45, 0.15
    else:
        sat = min(0.35, 0.10 + 0.05 * n_cand)
        cash = max(0.15, 0.30 - 0.03 * n_cand + 0.02 * n_avoid)
        core = max(0.20, 1.0 - cash - sat)
        # renormalize
        total = cash + core + sat
        cash, core, satellite = cash / total, core / total, sat / total
    return {
        "cash": round(cash, 3),
        "core_beta": round(core, 3),
        "satellite_research": round(satellite, 3),
        "note": (
            "Sleeve weights are a research hypothesis for paper staging — "
            "not an order ticket and not expected-return advice."
        ),
    }


def analyze_market(
    data: Mapping[str, pd.DataFrame],
    *,
    symbols: Sequence[str] | None = None,
    benchmark: str = "SPY",
) -> Dict[str, Any]:
    """Build multi-engine cross-sectional + regime scorecard."""
    syms = [s for s in (list(symbols) if symbols is not None else list(data.keys())) if s in data]
    mom63_map: Dict[str, float] = {}
    for sym in syms:
        close = data[sym]["close"].astype(float)
        m = _pct_change(close, 63)
        if m == m:
            mom63_map[sym] = m
    if mom63_map:
        ordered = sorted(mom63_map.values())

        def _pctile(v: float) -> float:
            return float(sum(1 for x in ordered if x <= v) / len(ordered))

        rs = {s: _pctile(v) for s, v in mom63_map.items()}
    else:
        rs = {s: 0.5 for s in syms}

    bench_close = (
        data[benchmark]["close"].astype(float) if benchmark in data else None
    )

    rows: List[Dict[str, Any]] = []
    for sym in syms:
        close = data[sym]["close"].astype(float)
        scored = score_symbol(
            close,
            rs_percentile=rs.get(sym, 0.5),
            df=data[sym],
            bench_close=bench_close,
        )
        scored["symbol"] = sym
        scored["last_close"] = _last_close(data[sym])
        rows.append(scored)

    rows.sort(
        key=lambda r: (
            float((r.get("scores") or {}).get("composite") or 0.0),
            float((r.get("scores") or {}).get("confidence") or 0.0),
        ),
        reverse=True,
    )

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

    # System posture narrative for the panel
    if cash_bias:
        posture = "DEFENSIVE"
        posture_detail = "Breadth/benchmark weak → cash bias engaged"
    elif n_cand >= 2:
        posture = "SELECTIVE_OFFENSE"
        posture_detail = "Multiple RESEARCH_CANDIDATE names — still paper/research only"
    else:
        posture = "NEUTRAL_WATCH"
        posture_detail = "No broad risk-on conviction — watchlist mode"

    return {
        "model": {
            "name": "WARDEN-X7",
            "version": "3.2",
            "engines": [
                "trend",
                "relative_strength",
                "risk_quality",
                "mean_reversion_pressure",
                "momentum_quality",
                "volume_thrust",
                "bench_decoupling",
            ],
            "ensemble": "weighted + disagreement confidence",
        },
        "benchmark": benchmark,
        "n_symbols": len(rows),
        "posture": {"code": posture, "detail": posture_detail},
        "regime": {
            "breadth_above_sma200": breadth if breadth == breadth else None,
            "benchmark_above_sma200": bench_trend,
            "risk_on_proxy": risk_on_proxy,
            "cash_bias": cash_bias,
        },
        "sleeve_hypothesis": _sleeve_hypothesis(rows, cash_bias=cash_bias),
        "action_counts": {"AVOID": n_avoid, "WATCH": n_watch, "RESEARCH_CANDIDATE": n_cand},
        "ranked": rows,
        "top_research": [r["symbol"] for r in rows if r["action"] == "RESEARCH_CANDIDATE"][:5],
        "avoid": [r["symbol"] for r in rows if r["action"] == "AVOID"],
        "disclaimer": (
            "WARDEN is a loss-mitigation / research triage command surface — "
            "NOT a buy list, NOT a guarantee of profit, NOT 'almost never lose', "
            "NOT a mega-returns engine. RESEARCH_CANDIDATE only means worth "
            "walk-forward re-run on owner-PC."
        ),
    }
