"""WARDEN-X9 engine core — maximal process complexity, zero return promises.

Each engine is point-in-time on the as-of bar. The meta-ensemble tilts weights
by regime and shrinks conviction when engines disagree. This maximizes the
*search intensity* for whatever OOS edge may exist; it does not claim mega gains.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd


def clip01(x: float) -> float:
    if x != x:
        return 0.0
    return float(min(max(x, 0.0), 1.0))


def pct_change(close: pd.Series, lookback: int) -> float:
    if len(close) <= lookback:
        return float("nan")
    a = float(close.iloc[-1])
    b = float(close.iloc[-1 - lookback])
    if b == 0 or b != b or a != a:
        return float("nan")
    return (a / b) - 1.0


def realized_vol(close: pd.Series, lookback: int = 21) -> float:
    if len(close) < lookback + 1:
        return float("nan")
    vol = float(close.pct_change().iloc[-lookback:].std(ddof=0))
    if vol != vol:
        return float("nan")
    return float(vol) * math.sqrt(252.0)


def rolling_max_dd(close: pd.Series, lookback: int = 63) -> float:
    if len(close) < 5:
        return float("nan")
    window = close.iloc[-min(lookback, len(close)) :]
    return float((window / window.cummax() - 1.0).min())


def above_ma(close: pd.Series, window: int) -> Optional[bool]:
    if len(close) < window:
        return None
    ma = float(close.rolling(window).mean().iloc[-1])
    px = float(close.iloc[-1])
    if ma != ma or px != px:
        return None
    return bool(px > ma)


def zscore_vs_ma(close: pd.Series, window: int = 20) -> float:
    if len(close) < window + 2:
        return float("nan")
    ma = close.rolling(window).mean()
    sd = close.rolling(window).std(ddof=0)
    m, s, px = float(ma.iloc[-1]), float(sd.iloc[-1]), float(close.iloc[-1])
    if s != s or s <= 1e-12 or m != m:
        return float("nan")
    return (px - m) / s


def momentum_hit_rate(close: pd.Series, lookback: int = 63) -> float:
    if len(close) < lookback + 1:
        return float("nan")
    rets = close.pct_change().iloc[-lookback:].dropna()
    if len(rets) < 10:
        return float("nan")
    return float((rets > 0).mean())


def volume_thrust(df: pd.DataFrame, lookback: int = 21) -> float:
    if "volume" not in df.columns or len(df) < lookback * 2:
        return float("nan")
    vol = df["volume"].astype(float)
    recent = float(vol.iloc[-lookback:].mean())
    prior = float(vol.iloc[-2 * lookback : -lookback].mean())
    if prior <= 0 or prior != prior or recent != recent:
        return float("nan")
    return clip01(0.5 + (recent / prior - 1.0))


def corr_to_bench(close: pd.Series, bench: pd.Series, lookback: int = 63) -> float:
    if len(close) < lookback + 2 or len(bench) < lookback + 2:
        return float("nan")
    a = close.pct_change().iloc[-lookback:]
    b = bench.reindex(close.index).pct_change().iloc[-lookback:]
    paired = pd.concat([a, b], axis=1).dropna()
    if len(paired) < 20:
        return float("nan")
    c = float(paired.iloc[:, 0].corr(paired.iloc[:, 1]))
    return c if c == c else float("nan")


def vol_of_vol(close: pd.Series, inner: int = 10, outer: int = 42) -> float:
    """Volatility-of-volatility — high = unstable risk regime."""
    if len(close) < outer + inner + 2:
        return float("nan")
    rets = close.pct_change()
    rolling = rets.rolling(inner).std(ddof=0)
    vov = float(rolling.iloc[-outer:].std(ddof=0))
    return vov if vov == vov else float("nan")


def trend_acceleration(close: pd.Series, fast: int = 20, slow: int = 50) -> float:
    """Signed acceleration of fast/slow spread (normalized)."""
    if len(close) < slow + 5:
        return float("nan")
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    spread = (f - s) / s.replace(0, pd.NA)
    if spread.isna().iloc[-1] or spread.isna().iloc[-5]:
        return float("nan")
    delta = float(spread.iloc[-1] - spread.iloc[-5])
    return delta


def drawdown_recovery_score(close: pd.Series, lookback: int = 126) -> float:
    """Higher = recovered from recent trough toward peak (healthier path)."""
    if len(close) < lookback:
        return float("nan")
    window = close.iloc[-lookback:]
    peak = float(window.max())
    trough = float(window.min())
    last = float(window.iloc[-1])
    if peak <= trough or peak != peak:
        return float("nan")
    # Where we sit between trough and peak
    return clip01((last - trough) / (peak - trough))


def gap_risk_score(df: pd.DataFrame, lookback: int = 63) -> float:
    """Lower overnight gap chaos → higher score (loss-mitigation friendly)."""
    if not {"open", "close"}.issubset(df.columns) or len(df) < lookback + 2:
        return 0.5
    o = df["open"].astype(float)
    c = df["close"].astype(float)
    gaps = (o / c.shift(1) - 1.0).iloc[-lookback:].dropna().abs()
    if len(gaps) < 10:
        return 0.5
    mean_gap = float(gaps.mean())
    return 1.0 - clip01(mean_gap / 0.02)


def multi_horizon_alignment(close: pd.Series) -> Tuple[float, Dict[str, Any]]:
    """All horizons same sign → high alignment (powerful trend coherence)."""
    moms = {h: pct_change(close, h) for h in (10, 21, 63, 126)}
    finite = {h: m for h, m in moms.items() if m == m}
    if len(finite) < 3:
        return 0.5, {"horizons": moms}
    signs = [1 if m > 0 else (-1 if m < 0 else 0) for m in finite.values()]
    agree = abs(sum(signs)) / len(signs)
    # Magnitude bonus when aligned positive
    mag = clip01(sum(max(m, 0.0) for m in finite.values()) / (0.08 * len(finite)))
    score = 0.65 * agree + 0.35 * mag
    return float(score), {"horizons": {str(k): (v if v == v else None) for k, v in moms.items()}}


ENGINE_NAMES: List[str] = [
    "trend",
    "relative_strength",
    "risk_quality",
    "mean_reversion_pressure",
    "momentum_quality",
    "volume_thrust",
    "bench_decoupling",
    "horizon_alignment",
    "vol_regime_stability",
    "path_recovery",
    "gap_stability",
    "trend_acceleration",
]


def base_weights(risk_on: bool) -> Dict[str, float]:
    """Regime-conditional ensemble weights (still research triage)."""
    if risk_on:
        return {
            "trend": 0.14,
            "relative_strength": 0.13,
            "risk_quality": 0.12,
            "mean_reversion_pressure": 0.04,
            "momentum_quality": 0.11,
            "volume_thrust": 0.07,
            "bench_decoupling": 0.05,
            "horizon_alignment": 0.12,
            "vol_regime_stability": 0.07,
            "path_recovery": 0.06,
            "gap_stability": 0.04,
            "trend_acceleration": 0.05,
        }
    # Defensive: overweight risk, gap, vol stability, path recovery
    return {
        "trend": 0.08,
        "relative_strength": 0.08,
        "risk_quality": 0.18,
        "mean_reversion_pressure": 0.05,
        "momentum_quality": 0.07,
        "volume_thrust": 0.05,
        "bench_decoupling": 0.06,
        "horizon_alignment": 0.08,
        "vol_regime_stability": 0.14,
        "path_recovery": 0.10,
        "gap_stability": 0.07,
        "trend_acceleration": 0.04,
    }


def run_engines(
    close: pd.Series,
    *,
    rs_percentile: float,
    df: pd.DataFrame | None = None,
    bench_close: pd.Series | None = None,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Compute all engine scores in [0,1] plus feature metadata."""
    meta: Dict[str, Any] = {}

    # Trend stack
    mom21, mom63, mom126 = pct_change(close, 21), pct_change(close, 63), pct_change(close, 126)
    a50, a200 = above_ma(close, 50), above_ma(close, 200)
    trend = 0.0
    for m, w in ((mom21, 0.25), (mom63, 0.4), (mom126, 0.35)):
        if m == m:
            trend += w * clip01(0.5 + m / 0.2)
    if a50 is True:
        trend = min(1.0, trend + 0.1)
    if a200 is True:
        trend = min(1.0, trend + 0.15)
    if a200 is False:
        trend = max(0.0, trend - 0.25)
    meta.update(
        {
            "mom_21": mom21 if mom21 == mom21 else None,
            "mom_63": mom63 if mom63 == mom63 else None,
            "mom_126": mom126 if mom126 == mom126 else None,
            "above_sma50": a50,
            "above_sma200": a200,
        }
    )

    # Risk
    vol = realized_vol(close, 21)
    mdd = rolling_max_dd(close, 63)
    risk = 0.55 * (1.0 - clip01((vol if vol == vol else 0.3) / 0.40)) + 0.45 * (
        1.0 - clip01(abs(mdd if mdd == mdd else -0.2) / 0.25)
    )
    meta.update({"vol_21_ann": vol if vol == vol else None, "max_dd_63": mdd if mdd == mdd else None})

    # Mean-rev pressure
    z = zscore_vs_ma(close, 20)
    mr = clip01(abs(z) / 2.5) if z == z else 0.5
    meta["z_ma20"] = float(z) if z == z else None

    # Momentum quality
    hit = momentum_hit_rate(close, 63)
    mq = clip01((hit - 0.35) / 0.30) if hit == hit else 0.5
    meta["hit_rate_63"] = float(hit) if hit == hit else None

    # Volume
    vt = volume_thrust(df) if df is not None else float("nan")
    vol_s = clip01(vt) if vt == vt else 0.5

    # Bench decoupling
    corr = corr_to_bench(close, bench_close, 63) if bench_close is not None else float("nan")
    corr_s = clip01(1.0 - abs(corr) * 0.35) if corr == corr else 0.5
    meta["corr_to_bench_63"] = float(corr) if corr == corr else None

    # Horizon alignment
    align, align_meta = multi_horizon_alignment(close)
    meta.update(align_meta)

    # Vol regime stability (inverse of vol-of-vol)
    vov = vol_of_vol(close)
    # Typical daily-vol std scale ~ small; map generously
    vol_stab = 1.0 - clip01((vov * math.sqrt(252.0) if vov == vov else 0.15) / 0.25)
    meta["vol_of_vol_ann"] = float(vov * math.sqrt(252.0)) if vov == vov else None

    # Path recovery
    recovery = drawdown_recovery_score(close, 126)
    path_s = recovery if recovery == recovery else 0.5
    meta["path_recovery_126"] = float(recovery) if recovery == recovery else None

    # Gap stability
    gap_s = gap_risk_score(df) if df is not None else 0.5

    # Trend acceleration → map to 0..1 (positive accel preferred in risk-on hunt)
    accel = trend_acceleration(close)
    accel_s = clip01(0.5 + (accel / 0.04 if accel == accel else 0.0))
    meta["trend_accel"] = float(accel) if accel == accel else None

    engines = {
        "trend": round(float(trend), 4),
        "relative_strength": round(clip01(float(rs_percentile)), 4),
        "risk_quality": round(float(risk), 4),
        "mean_reversion_pressure": round(float(mr), 4),
        "momentum_quality": round(float(mq), 4),
        "volume_thrust": round(float(vol_s), 4),
        "bench_decoupling": round(float(corr_s), 4),
        "horizon_alignment": round(float(align), 4),
        "vol_regime_stability": round(float(vol_stab), 4),
        "path_recovery": round(float(path_s), 4),
        "gap_stability": round(float(gap_s), 4),
        "trend_acceleration": round(float(accel_s), 4),
    }
    return engines, meta


def meta_ensemble(
    engines: Mapping[str, float],
    *,
    risk_on: bool,
) -> Dict[str, Any]:
    """Weighted composite + disagreement shrinkage + opportunity score."""
    weights = base_weights(risk_on)
    # Normalize in case of float drift
    wsum = sum(weights.values()) or 1.0
    weights = {k: v / wsum for k, v in weights.items()}
    raw = sum(float(engines.get(k, 0.5)) * weights[k] for k in weights)
    vals = [float(engines.get(k, 0.5)) for k in weights]
    disagree = float(pd.Series(vals).std(ddof=0)) if vals else 0.0
    confidence = clip01(1.0 - disagree * 2.0)
    # Shrink composite toward neutral when engines fight
    composite = 0.5 + (raw - 0.5) * confidence
    # Opportunity = how hard we'd hunt this name in research (not expected return)
    opportunity = clip01(composite * (0.55 + 0.45 * confidence))
    return {
        "raw_composite": round(float(raw), 4),
        "composite": round(float(composite), 4),
        "confidence": round(float(confidence), 4),
        "disagreement": round(float(disagree), 4),
        "opportunity": round(float(opportunity), 4),
        "engine_weights": {k: round(v, 4) for k, v in weights.items()},
        "regime_weight_mode": "risk_on" if risk_on else "defensive",
    }
