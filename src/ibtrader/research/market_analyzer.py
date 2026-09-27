"""WARDEN multi-engine market analyzer (research triage — not a profit promise).

Delegates scoring to ``warden_engines`` (12 engines + regime-conditional
meta-ensemble). Complexity maximizes search intensity for OOS candidates;
it does **not** claim mega returns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from ..intelligence.regime import compute_breadth
from .warden_engines import ENGINE_NAMES, meta_ensemble, run_engines


def _last_close(df: pd.DataFrame) -> Optional[float]:
    if df is None or df.empty or "close" not in df.columns:
        return None
    v = float(df["close"].astype(float).iloc[-1])
    return v if v == v else None


def score_symbol(
    close: pd.Series,
    *,
    rs_percentile: float,
    df: pd.DataFrame | None = None,
    bench_close: pd.Series | None = None,
    risk_on: bool = True,
) -> Dict[str, Any]:
    """Full X9 engine stack + meta-ensemble for one symbol."""
    engines, meta = run_engines(
        close, rs_percentile=rs_percentile, df=df, bench_close=bench_close
    )
    ens = meta_ensemble(engines, risk_on=risk_on)

    above200 = meta.get("above_sma200")
    mdd = meta.get("max_dd_63")
    vol = meta.get("vol_21_ann")
    rs_score = float(engines.get("relative_strength") or 0.0)
    risk_s = float(engines.get("risk_quality") or 0.0)
    composite = float(ens["composite"])
    confidence = float(ens["confidence"])
    opportunity = float(ens["opportunity"])

    action = "AVOID"
    if (
        opportunity >= 0.58
        and composite >= 0.60
        and confidence >= 0.42
        and above200 is not False
        and rs_score >= 0.52
        and risk_s >= 0.38
    ):
        action = "RESEARCH_CANDIDATE"
    elif composite >= 0.45 or opportunity >= 0.48:
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
    if ens["disagreement"] > 0.26:
        risk_flags.append("engine_disagreement")
    if confidence < 0.35:
        risk_flags.append("low_ensemble_confidence")
    if float(engines.get("vol_regime_stability") or 1.0) < 0.35:
        risk_flags.append("unstable_vol_regime")
    if risk_flags and action == "RESEARCH_CANDIDATE":
        action = "WATCH"

    return {
        **meta,
        "rs_percentile": rs_score,
        "engines": engines,
        "engine_weights": ens["engine_weights"],
        "scores": {
            "trend": engines["trend"],
            "relative_strength": engines["relative_strength"],
            "risk_quality": engines["risk_quality"],
            "raw_composite": ens["raw_composite"],
            "composite": ens["composite"],
            "confidence": ens["confidence"],
            "disagreement": ens["disagreement"],
            "opportunity": ens["opportunity"],
        },
        "meta": {
            "regime_weight_mode": ens["regime_weight_mode"],
            "n_engines": len(engines),
        },
        "action": action,
        "risk_flags": risk_flags,
    }


def _sleeve_hypothesis(
    rows: Sequence[Mapping[str, Any]],
    *,
    cash_bias: bool,
) -> Dict[str, Any]:
    n = len(rows)
    cands = [r for r in rows if r.get("action") == "RESEARCH_CANDIDATE"]
    n_cand = len(cands)
    n_avoid = sum(1 for r in rows if r.get("action") == "AVOID")
    if cash_bias or n == 0:
        cash, core, satellite = 0.55, 0.35, 0.10
    elif n_cand == 0:
        cash, core, satellite = 0.40, 0.45, 0.15
    else:
        sat = min(0.40, 0.12 + 0.06 * n_cand)
        cash = max(0.12, 0.28 - 0.04 * n_cand + 0.02 * n_avoid)
        core = max(0.20, 1.0 - cash - sat)
        total = cash + core + sat
        cash, core, satellite = cash / total, core / total, sat / total

    # Opportunity-weighted satellite names (research paper sleeve only)
    sat_names: List[Dict[str, Any]] = []
    if cands and satellite > 0:
        opps = [max(float((c.get("scores") or {}).get("opportunity") or 0.01), 0.01) for c in cands]
        ssum = sum(opps) or 1.0
        for c, o in zip(cands, opps):
            sat_names.append(
                {
                    "symbol": c.get("symbol"),
                    "weight_in_satellite": round(o / ssum, 4),
                    "opportunity": round(o, 4),
                }
            )

    return {
        "cash": round(cash, 3),
        "core_beta": round(core, 3),
        "satellite_research": round(satellite, 3),
        "satellite_names": sat_names,
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
    """Build multi-engine cross-sectional + regime scorecard (WARDEN-X9)."""
    syms = [s for s in (list(symbols) if symbols is not None else list(data.keys())) if s in data]
    from .warden_engines import pct_change

    mom63_map: Dict[str, float] = {}
    for sym in syms:
        m = pct_change(data[sym]["close"].astype(float), 63)
        if m == m:
            mom63_map[sym] = m
    if mom63_map:
        ordered = sorted(mom63_map.values())

        def _pctile(v: float) -> float:
            return float(sum(1 for x in ordered if x <= v) / len(ordered))

        rs = {s: _pctile(v) for s, v in mom63_map.items()}
    else:
        rs = {s: 0.5 for s in syms}

    bench_close = data[benchmark]["close"].astype(float) if benchmark in data else None

    breadth = float("nan")
    try:
        b = compute_breadth(dict(data), long_ma=200)
        if len(b):
            breadth = float(b.iloc[-1])
    except Exception:
        breadth = float("nan")

    from .warden_engines import above_ma

    bench_trend = None
    if benchmark in data:
        bench_trend = above_ma(data[benchmark]["close"].astype(float), 200)

    risk_on_proxy = bool((breadth == breadth and breadth >= 0.55) and (bench_trend is not False))
    cash_bias = not risk_on_proxy

    rows: List[Dict[str, Any]] = []
    for sym in syms:
        close = data[sym]["close"].astype(float)
        scored = score_symbol(
            close,
            rs_percentile=rs.get(sym, 0.5),
            df=data[sym],
            bench_close=bench_close,
            risk_on=risk_on_proxy,
        )
        scored["symbol"] = sym
        scored["last_close"] = _last_close(data[sym])
        rows.append(scored)

    rows.sort(
        key=lambda r: (
            float((r.get("scores") or {}).get("opportunity") or 0.0),
            float((r.get("scores") or {}).get("composite") or 0.0),
            float((r.get("scores") or {}).get("confidence") or 0.0),
        ),
        reverse=True,
    )

    n_avoid = sum(1 for r in rows if r["action"] == "AVOID")
    n_watch = sum(1 for r in rows if r["action"] == "WATCH")
    n_cand = sum(1 for r in rows if r["action"] == "RESEARCH_CANDIDATE")

    if cash_bias:
        posture = "DEFENSIVE"
        posture_detail = "Breadth/benchmark weak → cash bias; hunt quality not force"
    elif n_cand >= 2:
        posture = "SELECTIVE_OFFENSE"
        posture_detail = "Multiple high-opportunity RESEARCH_CANDIDATE names — paper/research only"
    else:
        posture = "NEUTRAL_WATCH"
        posture_detail = "No broad risk-on conviction — watchlist / deepen diagnostics"

    mean_opp = (
        float(sum(float((r.get("scores") or {}).get("opportunity") or 0.0) for r in rows) / len(rows))
        if rows
        else 0.0
    )
    mean_conf = (
        float(sum(float((r.get("scores") or {}).get("confidence") or 0.0) for r in rows) / len(rows))
        if rows
        else 0.0
    )

    return {
        "model": {
            "name": "WARDEN-X9",
            "version": "3.9",
            "engines": list(ENGINE_NAMES),
            "n_engines": len(ENGINE_NAMES),
            "ensemble": "regime-conditional weights + disagreement shrinkage + opportunity rank",
            "search_intensity": {
                "mean_opportunity": round(mean_opp, 4),
                "mean_confidence": round(mean_conf, 4),
                "note": (
                    "High search intensity ≠ expected mega returns. "
                    "It means the stack is pressing hard on triage quality."
                ),
            },
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
        "top_opportunity": [
            {
                "symbol": r["symbol"],
                "opportunity": (r.get("scores") or {}).get("opportunity"),
                "action": r.get("action"),
            }
            for r in rows[:5]
        ],
        "avoid": [r["symbol"] for r in rows if r["action"] == "AVOID"],
        "disclaimer": (
            "WARDEN-X9 is a maximal-complexity loss-mitigation / research triage stack — "
            "NOT a buy list, NOT a guarantee of profit, NOT 'almost never lose', "
            "NOT a mega-returns engine. Opportunity rank only prioritizes walk-forward "
            "re-runs on owner-PC."
        ),
    }
