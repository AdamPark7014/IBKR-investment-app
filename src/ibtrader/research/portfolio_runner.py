"""Phase-2 portfolio research: the stage-graph system against 60/40, All Weather and random portfolios.

For every configuration the engine runs ``PipelineStrategy`` (weight mode) over the
universe with the risk/cost settings of ``AppSettings``; the out-of-sample window
starts at ``SystemOutput.warmup_end`` (every stage has a value for >= 2 symbols)
and ends at the last bar left after the phase-1 hold-out. Benchmarks are computed
on exactly that window and the strict gates decide the verdict against the 60/40.

Statistics: candidate OOS stats and the benchmark stats that feed the gates are
both computed with ``backtest.metrics.compute_stats`` on an equity curve (so the
candidate and the 60/40 use the same Sharpe / max_dd definition). The
``research.benchmarks.returns_stats`` block of each benchmark is reported next
to it (``stats_returns``) for cross-checking, not for gating.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..backtest.engine import BacktestResult, backtest, restricted_counts
from ..backtest.metrics import compute_stats
from ..config import AppSettings
from ..data.universe import UniverseSpec
from ..ops.artifacts import config_hash, dataset_hash, git_commit
from ..pipeline.rules import DEFAULT_RULES
from ..pipeline.system import SystemConfig
from ..risk.manager import RiskManager, RiskState
from ..strategy.pipeline_strategy import PipelineStrategy
from .benchmarks import (
    all_weather_static,
    random_long_only_portfolios,
    returns_stats,
    sharpe_percentile,
    sixty_forty,
)
from .dsr import deflated_sharpe_ratio, sharpe_std_error
from .gates import compute_trial_budget, evaluate_strict_gates
from .pbo import probability_of_backtest_overfitting
from .runner import build_experiment_records
from .suite import apply_holdout

Profile = Literal["smoke", "full"]

log = logging.getLogger("ibtrader.research.portfolio_runner")

PHASE = "phase2-portfolio"
RANDOM_PORTFOLIOS = {"smoke": 100, "full": 1000}
RANDOM_SEED = 0
BENCHMARK_REBALANCE = "M"
BENCHMARK_COST_BPS = 5.0
INITIAL_EQUITY = 100_000.0

RECOMMENDATION_FAIL = (
    "Nada gana al 60/40 con gates estrictos: indexar (AOR o 60/40 pasivo) y mantener el repo como laboratorio."
)
RECOMMENDATION_PASS = "Paper 2–3 meses con la configuración congelada antes de capital."

INSTRUMENT_WEIGHTINGS: Tuple[str, ...] = ("box_risk_parity", "hrp", "equal")

# Statistical gates on top of ``evaluate_strict_gates`` (playbook: t >= 3, DSR, PBO, frozen hold-out).
MIN_T_STAT = 3.0
MIN_RANDOM_PERCENTILE = 95.0
PBO_BLOCKS = 10
PBO_MIN_BLOCK_DAYS = 20
TRIALS_LEDGER = "portfolio_trials.jsonl"
SELECTION_RULE = "max DSR among gate-passing candidates (tie-break: t-stat, then shallower max_dd)"


def rule_sets() -> Dict[str, Tuple[str, ...]]:
    """Named rule subsets of ``DEFAULT_RULES`` used by the ``full`` grid (empty sets are dropped)."""
    default = tuple(DEFAULT_RULES)
    sets = {
        "default": default,
        "ewmac": tuple(r for r in default if r.startswith("ewmac")),
        "tsmom": tuple(r for r in default if r.startswith("tsmom")),
    }
    return {k: v for k, v in sets.items() if v}


def portfolio_candidates(profile: str) -> List[Tuple[str, Tuple[str, ...], str]]:
    """``(candidate_id, rules, instrument_weighting)`` per configuration of ``profile``.

    * ``smoke``: one configuration (``DEFAULT_RULES`` × ``box_risk_parity``).
    * ``full``: small grid rules (default | ewmac only | tsmom only) × weighting
      (box_risk_parity | hrp | equal). Every configuration counts as one trial.
    """
    if profile == "smoke":
        return [("pipeline_default_box_risk_parity", tuple(DEFAULT_RULES), "box_risk_parity")]
    if profile == "full":
        return [
            (f"pipeline_{rs_name}_{weighting}", rules, weighting)
            for rs_name, rules in rule_sets().items()
            for weighting in INSTRUMENT_WEIGHTINGS
        ]
    raise ValueError(f"unknown profile {profile!r}: expected 'smoke' or 'full'")


# --------------------------------------------------------------------------- helpers


def _noneify(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _noneify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_noneify(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _years_span(index: pd.Index) -> float:
    if len(index) < 2:
        return 0.0
    delta = pd.Timestamp(index.max()) - pd.Timestamp(index.min())
    return float(delta.days) / 365.25


def close_frame(data: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Closes as a (dates × symbols) frame on the union of the symbol indexes."""
    frame = pd.DataFrame({sym: df["close"].astype(float) for sym, df in data.items()})
    frame.index = pd.DatetimeIndex(frame.index)
    return frame.sort_index()


def _returns_to_equity(returns: pd.Series, capital: float) -> Tuple[pd.Series, pd.Series]:
    r = pd.Series(returns, dtype=float).sort_index().fillna(0.0)
    eq = (1.0 + r).cumprod() * float(capital)
    return eq, r


def _equity_stats(equity: pd.Series, returns: pd.Series) -> Dict[str, Any]:
    st = compute_stats(equity, returns)
    return {
        "cagr": float(st.cagr),
        "sharpe": float(st.sharpe),
        "sortino": float(st.sortino),
        "calmar": float(st.calmar),
        "max_dd": float(st.max_drawdown),
        "max_drawdown": float(st.max_drawdown),
        "volatility": float(st.volatility),
        "total_return": float(st.total_return),
        "win_rate": float(st.win_rate),
        "n_days": int(len(equity)),
    }


def _sharpe_from_returns(returns: pd.Series) -> float:
    """Same definition as ``compute_stats`` (ddof=0, 252 periods) for the random portfolios."""
    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < 2:
        return float("nan")
    vol = float(r.std(ddof=0))
    if vol <= 0.0 or not math.isfinite(vol):
        return float("nan")
    return float(r.mean() / vol * math.sqrt(252.0))


def _random_sharpes(random_out: Any) -> List[float]:
    """Sharpes of ``random_long_only_portfolios``: a stats frame (``sharpe`` column) or a returns frame."""
    if isinstance(random_out, pd.DataFrame):
        if "sharpe" in random_out.columns:
            values = random_out["sharpe"].astype(float).tolist()
        else:
            values = [_sharpe_from_returns(random_out[c]) for c in random_out.columns]
    elif isinstance(random_out, pd.Series):
        values = random_out.astype(float).tolist()
    else:
        values = [float(v) for v in random_out]
    return [v for v in values if math.isfinite(v)]


def sixty_forty_legs(symbols: Sequence[str], universe: Optional[UniverseSpec]) -> Tuple[str, str]:
    """``(equity, bonds)`` legs for the 60/40: SPY/IEF when present, else by box, else the first two symbols."""
    syms = list(symbols)
    if not syms:
        raise ValueError("sixty_forty_legs: no symbols")
    equity = "SPY" if "SPY" in syms else None
    bonds = "IEF" if "IEF" in syms else None
    if universe is not None:
        for sym in syms:
            entry = universe.get(sym)
            if entry is None:
                continue
            box = (entry.box or "").lower()
            cls = (entry.asset_class or "").lower()
            if equity is None and ("equity" in box or cls == "equity"):
                equity = sym
            if bonds is None and ("treasur" in box or cls == "fixed_income"):
                bonds = sym
    if equity is None:
        equity = syms[0]
    if bonds is None:
        bonds = next((s for s in syms if s != equity), equity)
    return equity, bonds


def _benchmark_block(
    name: str, returns: pd.Series, capital: float, extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    eq, r = _returns_to_equity(returns, capital)
    block: Dict[str, Any] = {"name": name, "stats": _equity_stats(eq, r)}
    try:
        block["stats_returns"] = {k: float(v) for k, v in dict(returns_stats(r)).items()}
    except Exception as exc:  # cross-check only; never blocks the verdict
        block["stats_returns"] = None
        block["stats_returns_error"] = f"{type(exc).__name__}: {exc}"
    if extra:
        block.update(extra)
    return block


def benchmark_window_prices(
    prices: pd.DataFrame, start: Optional[pd.Timestamp] = None
) -> Tuple[pd.DataFrame, List[str]]:
    """Prices of the evaluated window ``[start, end]`` and the symbols excluded from the benchmarks.

    A symbol enters the benchmarks only if it has a price on the window's first bar (carrying its
    last known close forward, so a bar it skipped does not exclude it). A symbol that lists later
    would make every fixed-weight benchmark start when it lists — a different window from the
    candidate's — so it is excluded instead, with a warning and in ``excluded_symbols``.
    """
    px = prices.astype(float).sort_index().ffill()
    if start is not None:
        px = px.loc[pd.Timestamp(start):]
    if len(px) == 0:
        raise ValueError("benchmark window is empty")
    first = px.iloc[0]
    excluded = [str(c) for c in px.columns if pd.isna(first[c])]
    if excluded:
        log.warning(
            "benchmarks_excluded_late_listing symbols=%s window_start=%s", excluded, str(px.index[0])
        )
    keep = [c for c in px.columns if str(c) not in excluded]
    if not keep:
        raise ValueError(f"no symbol has a price on the first bar of the benchmark window {px.index[0]}")
    return px[keep], excluded


def compute_benchmarks(
    prices: pd.DataFrame,
    universe: Optional[UniverseSpec],
    capital: float = INITIAL_EQUITY,
    n_random: int = RANDOM_PORTFOLIOS["smoke"],
    seed: int = RANDOM_SEED,
    start: Optional[pd.Timestamp] = None,
) -> Dict[str, Any]:
    """60/40, static All Weather and random long-only portfolios on exactly the candidate's window.

    ``start`` (the candidate's ``warmup_end``) opens the window; every benchmark runs from that bar
    to the last one (``benchmark_window_prices``). Symbols without a price on the first bar are
    excluded from all benchmarks and listed in ``excluded_symbols`` / ``note``; a 60/40 leg or All
    Weather component among them is replaced (leg) or dropped and renormalised (component), never
    allowed to move the window.

    Returns ``{"sixty_forty", "all_weather", "random", "window", "excluded_symbols"}``;
    ``random["sharpes"]`` keeps the full distribution for ``sharpe_percentile`` (dropped from the
    written summary). A benchmark whose inputs are missing is ``None`` with ``*_error``.
    """
    window_px, excluded = benchmark_window_prices(prices, start)
    window = {
        "start": str(window_px.index[0]),
        "end": str(window_px.index[-1]),
        "n_bars": int(len(window_px)),
    }
    equity_leg, bond_leg = sixty_forty_legs(list(window_px.columns), universe)
    out: Dict[str, Any] = {"window": window, "excluded_symbols": excluded}
    if excluded:
        out["note"] = (
            f"excluded from every benchmark (no price on the window's first bar {window['start']}): "
            f"{', '.join(excluded)}"
        )
    sf = sixty_forty(
        window_px, equity=equity_leg, bonds=bond_leg, rebalance=BENCHMARK_REBALANCE, cost_bps=BENCHMARK_COST_BPS
    )
    out["sixty_forty"] = _benchmark_block(
        "sixty_forty", sf, capital, {"equity": equity_leg, "bonds": bond_leg, "rebalance": BENCHMARK_REBALANCE}
    )
    try:
        aw = all_weather_static(window_px, rebalance=BENCHMARK_REBALANCE, cost_bps=BENCHMARK_COST_BPS)
        out["all_weather"] = _benchmark_block(
            "all_weather",
            aw,
            capital,
            {"rebalance": BENCHMARK_REBALANCE, "dropped": list(aw.attrs.get("dropped") or []),
             "weights": dict(aw.attrs.get("weights") or {})},
        )
    except Exception as exc:
        out["all_weather"] = None
        out["all_weather_error"] = f"{type(exc).__name__}: {exc}"
    rnd = random_long_only_portfolios(
        window_px, n=int(n_random), seed=int(seed), rebalance=BENCHMARK_REBALANCE, cost_bps=BENCHMARK_COST_BPS
    )
    sharpes = _random_sharpes(rnd)
    s = pd.Series(sharpes, dtype=float)
    out["random"] = {
        "n": int(n_random),
        "n_valid": int(len(sharpes)),
        "seed": int(seed),
        "symbols": [str(c) for c in window_px.columns],
        "sharpe_p5": float(s.quantile(0.05)) if len(s) else None,
        "sharpe_p50": float(s.quantile(0.50)) if len(s) else None,
        "sharpe_p95": float(s.quantile(0.95)) if len(s) else None,
        "sharpe_mean": float(s.mean()) if len(s) else None,
        "sharpes": sharpes,
    }
    return out


def _public_benchmarks(bench: Mapping[str, Any]) -> Dict[str, Any]:
    pub = dict(bench)
    rnd = pub.get("random")
    if isinstance(rnd, Mapping):
        pub["random"] = {k: v for k, v in rnd.items() if k != "sharpes"}
    return pub


def _window_stats(res: BacktestResult, start: pd.Timestamp, capital: float) -> Dict[str, Any]:
    """Candidate stats on ``[start, end]`` from the engine's equity curve (``compute_stats``)."""
    eq = res.equity_curve.loc[start:]
    rets = res.returns.reindex(eq.index).fillna(0.0)
    stats = _equity_stats(eq, rets)
    years = _years_span(eq.index)
    trades_in = [t for t in res.trades if pd.Timestamp(t[0]) >= start]
    notional = float(sum(abs(int(t[2])) * float(t[3]) for t in trades_in))
    turnover = notional / float(capital) if capital else 0.0
    total_costs = float(getattr(res.stats, "total_costs", 0.0) or 0.0)
    # Cost drag over the evaluated window's years (``res.stats`` divides by the whole backtest span).
    cost_drag = total_costs / capital / years * 100.0 if (capital and years > 0) else 0.0
    stats.update(
        {
            "trade_count": int(len(trades_in)),
            "turnover": float(turnover),
            "turnover_annual": float(turnover / years) if years > 0 else 0.0,
            "total_costs": total_costs,
            "total_commission": float(getattr(res.stats, "total_commission", 0.0) or 0.0),
            "avg_cost_bps_per_order": float(getattr(res.stats, "avg_cost_bps_per_order", 0.0) or 0.0),
            "cost_drag_annual_pct": float(cost_drag),
            "years": float(years),
            "oos_start": str(eq.index.min()) if len(eq) else None,
            "oos_end": str(eq.index.max()) if len(eq) else None,
        }
    )
    return stats


def _finite(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _selection_key(row: Mapping[str, Any]) -> Tuple[float, float, float]:
    """DSR first (it already deflates for skew, kurtosis, sample length and the number of trials)."""
    diag = row.get("diagnostics") or {}
    dsr = _finite((diag.get("dsr") or {}).get("dsr"))
    t_stat = _finite(diag.get("t_stat"))
    max_dd = _finite((row.get("oos") or {}).get("max_dd"))
    return (
        dsr if dsr is not None else float("-inf"),
        t_stat if t_stat is not None else float("-inf"),
        max_dd if max_dd is not None else float("-inf"),  # drawdowns are negative: higher = shallower
    )


def _best_row(rows: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """``SELECTION_RULE``: the gate-passing candidate with the highest DSR, never the raw best Sharpe.

    With nothing passing, the highest-DSR candidate is still reported (for diagnosis) but the
    verdict stays FAIL.
    """
    if not rows:
        return None
    passed = [r for r in rows if r.get("gate_passed")]
    pool = passed or list(rows)
    return max(pool, key=_selection_key)


def _window_returns(res: BacktestResult, start: pd.Timestamp) -> pd.Series:
    """Daily returns strictly after ``start`` (the return of ``start`` belongs to the warm-up book)."""
    r = res.returns.loc[start:].astype(float)
    return r.iloc[1:] if len(r) else r


def daily_return_diagnostics(returns: pd.Series) -> Dict[str, Any]:
    """Per-period Sharpe, its t-statistic (``SR·√n``), skew and Pearson kurtosis of daily returns."""
    r = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    n = int(len(r))
    out: Dict[str, Any] = {"n_obs": n, "sr_daily": float("nan"), "t_stat": float("nan"), "skew": 0.0,
                           "kurtosis": 3.0}
    if n < 3:
        return out
    sd = float(r.std(ddof=1))
    if not (sd > 0.0 and math.isfinite(sd)):
        return out
    sr = float(r.mean()) / sd
    skew = float(r.skew())
    kurt = float(r.kurt()) + 3.0  # pandas gives excess kurtosis
    out.update(
        {
            "sr_daily": sr,
            "sr_annual": sr * math.sqrt(252.0),
            "t_stat": sr * math.sqrt(n),
            "skew": skew if math.isfinite(skew) else 0.0,
            "kurtosis": kurt if math.isfinite(kurt) else 3.0,
        }
    )
    return out


def dsr_block(diag: Mapping[str, Any], trial_sharpes: Sequence[float], n_trials: int) -> Dict[str, Any]:
    """Deflated Sharpe (Bailey & López de Prado) on daily returns; PSR vs 0 when there is one trial."""
    sr = _finite(diag.get("sr_daily"))
    n_obs = int(diag.get("n_obs") or 0)
    if sr is None or n_obs < 3:
        return {"dsr": float("nan"), "method": "undefined", "note": "no finite daily Sharpe"}
    skew = float(diag.get("skew") or 0.0)
    kurt = float(diag.get("kurtosis") or 3.0)
    trials = [float(x) for x in trial_sharpes if _finite(x) is not None]
    if int(n_trials) < 2 or len(trials) < 2:
        se = sharpe_std_error(sr, n_obs, skew=skew, kurtosis=kurt)
        z = sr / se
        return {
            "dsr": float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))),
            "method": "psr_single_trial",
            "observed_sr": sr,
            "sr0_benchmark": 0.0,
            "sr_std_error": se,
            "n_obs": n_obs,
            "n_trials": int(n_trials),
            "skew": skew,
            "kurtosis": kurt,
        }
    out = deflated_sharpe_ratio(sr, n_obs=n_obs, n_trials=int(n_trials), trial_sharpes=trials, skew=skew,
                                kurtosis=kurt)
    out["method"] = "dsr"
    return out


def pbo_block(returns_by_candidate: Mapping[str, pd.Series]) -> Dict[str, Any]:
    """CSCV PBO over ``PBO_BLOCKS`` contiguous blocks of the window every candidate shares.

    Not applicable with a single configuration (nothing was selected). With several candidates but
    a common window shorter than ``PBO_BLOCKS × PBO_MIN_BLOCK_DAYS`` the PBO is undefined and the
    gate fails (``pbo_unavailable``): an unmeasured selection bias is not a pass.
    """
    frame = pd.DataFrame({cid: pd.Series(r, dtype=float) for cid, r in returns_by_candidate.items()})
    frame = frame.dropna(how="any")
    if frame.shape[1] < 2:
        return {"pbo": float("nan"), "applicable": False, "note": "single configuration: no selection to overfit"}
    n = int(len(frame))
    if n < PBO_BLOCKS * PBO_MIN_BLOCK_DAYS:
        return {
            "pbo": float("nan"),
            "applicable": True,
            "n_days": n,
            "note": f"common window {n} days < {PBO_BLOCKS}×{PBO_MIN_BLOCK_DAYS}",
        }
    mat = np.full((frame.shape[1], PBO_BLOCKS), np.nan, dtype=float)
    for j, idx in enumerate(np.array_split(np.arange(n), PBO_BLOCKS)):
        sub = frame.iloc[idx]
        sd = sub.std(ddof=1).replace(0.0, np.nan)
        mat[:, j] = (sub.mean() / sd).to_numpy(dtype=float)
    out = probability_of_backtest_overfitting(mat)
    out.update(
        {
            "applicable": True,
            "n_days": n,
            "blocks": PBO_BLOCKS,
            "window_start": str(frame.index.min()),
            "window_end": str(frame.index.max()),
            "candidates": list(frame.columns),
        }
    )
    return out


def portfolio_extra_gates(
    diag: Mapping[str, Any],
    dsr: Mapping[str, Any],
    pbo: Mapping[str, Any],
    random_percentile: Optional[float],
    holdout: Mapping[str, Any],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Gates ``evaluate_strict_gates`` does not enforce by itself: t ≥ 3, defined DSR/PBO,
    percentile ≥ 95 vs random long-only portfolios and a declared frozen hold-out."""
    reasons: List[str] = []
    t_stat = _finite(diag.get("t_stat"))
    t_ok = t_stat is not None and t_stat >= MIN_T_STAT
    if not t_ok:
        reasons.append(f"t_stat={t_stat if t_stat is not None else float('nan'):.2f} < {MIN_T_STAT}")
    dsr_val = _finite(dsr.get("dsr"))
    dsr_defined = dsr_val is not None
    if not dsr_defined:
        reasons.append("dsr_undefined")
    pbo_ok = True
    if pbo.get("applicable") and _finite(pbo.get("pbo")) is None:
        pbo_ok = False
        reasons.append(f"pbo_unavailable ({pbo.get('note')})")
    pct_ok = random_percentile is not None and float(random_percentile) >= MIN_RANDOM_PERCENTILE
    if not pct_ok:
        reasons.append(f"random_sharpe_percentile={random_percentile} < {MIN_RANDOM_PERCENTILE}")
    holdout_declared = bool(holdout.get("holdout_start"))
    if not holdout_declared:
        reasons.append("holdout_not_declared: set RESEARCH__HOLDOUT_START before trusting a PASS")
    checks = {
        "t_stat": t_stat,
        "min_t_stat": MIN_T_STAT,
        "t_stat_ok": t_ok,
        "dsr_defined": dsr_defined,
        "pbo": _finite(pbo.get("pbo")),
        "pbo_applicable": bool(pbo.get("applicable")),
        "pbo_ok": pbo_ok,
        "random_sharpe_percentile": random_percentile,
        "min_random_percentile": MIN_RANDOM_PERCENTILE,
        "random_percentile_ok": pct_ok,
        "holdout_declared": holdout_declared,
    }
    passed = t_ok and dsr_defined and pbo_ok and pct_ok and holdout_declared
    return passed, reasons, checks


#: Realised vol below this share of ``tau`` with the cap binding often = the target is not reachable.
VOL_SHORTFALL_RATIO = 0.75


def vol_target_diagnostics(
    cfg: SystemConfig, out: Any, start: pd.Timestamp, oos: Mapping[str, Any]
) -> Dict[str, Any]:
    """Requested ``tau`` vs what the evaluated window delivered under the ``max_leverage`` cap.

    With ``max_leverage = 1.0`` (no margin) the system asks for 10 % but the gross cap binds most
    days and the realised volatility is the **effective** target. Raising the cap is Adam's call.
    """
    capped = getattr(out, "leverage_capped", None)
    window = capped.loc[start:] if isinstance(capped, pd.Series) and len(capped) else pd.Series(dtype=bool)
    binding = float(window.astype(float).mean()) if len(window) else 0.0
    realised = _finite(oos.get("volatility"))
    shortfall = bool(realised is not None and realised < VOL_SHORTFALL_RATIO * float(cfg.tau))
    note = None
    if shortfall:
        note = (
            f"tau {cfg.tau:.0%} requested, {realised:.1%} realised; the max_leverage {cfg.max_leverage:g} cap "
            f"bound {binding:.0%} of days: the effective vol target is ~{realised:.1%}. Reaching {cfg.tau:.0%} "
            "needs more gross exposure (e.g. 1.5x on margin) — Adam's decision, not a default."
        )
    return {
        "tau_requested": float(cfg.tau),
        "max_leverage": float(cfg.max_leverage),
        "realised_vol_annual": realised,
        "leverage_cap_binding_frac": binding,
        "effective_vol_target": realised,
        "shortfall": shortfall,
        "note": note,
    }


def _trial_key(candidate_id: str, params: Mapping[str, Any]) -> str:
    """Identity of a configuration across runs (same rules/weighting/knobs = same trial)."""
    blob = json.dumps({"candidate_id": candidate_id, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load_trials_ledger(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Latest row per configuration key from the cross-run trial ledger (empty when absent)."""
    out: Dict[str, Dict[str, Any]] = {}
    if path is None or not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("trial_key"):
            out[str(row["trial_key"])] = row
    return out


# --------------------------------------------------------------------------- the runner


def run_portfolio_research(
    data: Dict[str, pd.DataFrame],
    settings: AppSettings,
    universe: UniverseSpec,
    profile: Profile = "smoke",
    exp_id: str = "",
    reports_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the phase-2 system over ``data`` and report an honest verdict.

    Steps, in order:

    1. Phase-1 hold-out via ``research.suite.apply_holdout`` (reference symbol = the
       configured benchmark when loaded, else the first symbol): bars on/after
       ``settings.research.holdout_start`` are hidden unless ``confirmation_mode``.
    2. ``SystemConfig`` per candidate (``portfolio_candidates``) with the boxes of
       ``universe``, ``capital = 100 000``, ``max_leverage = 1.0`` (engine cap) and
       ``long_only`` / ``short_only`` from ``settings.trading.direction``. With the 1.0 cap the
       10 % ``tau`` is not reachable: ``vol_target`` reports the realised (effective) target.
    3. ``backtest`` with ``PipelineStrategy`` and the commission / slippage / reg-fee /
       risk settings (RiskManager on, no regime veto: the pipeline has its own sizing).
    4. OOS window = ``[warmup_end, last bar]``; ``warmup_end is None`` → FAIL ``no_warmup``.
    5. Benchmarks on the same window (``compute_benchmarks``); ``bh_stats`` for the
       gates = the 60/40 stats; ``restricted_bar_frac`` from ``restricted_counts``.
    6. Diagnostics on the daily returns of the evaluated window: t-statistic
       (``SR_daily·√n``), DSR over every trial (this run + ``<reports_dir>/research/
       portfolio_trials.jsonl``), PBO (CSCV over ``PBO_BLOCKS`` blocks of the window
       all candidates share) and the Sharpe percentile against random long-only
       portfolios.
    7. ``evaluate_strict_gates`` (beat the 60/40, DSR ≥ 0.95, PBO < 0.5, trial budget on
       the evaluated window's years, hold-out discipline) plus ``portfolio_extra_gates``
       (t ≥ 3, percentile ≥ 95, defined DSR/PBO, declared hold-out). All must hold.
    8. Selection (``SELECTION_RULE``): highest DSR among passing candidates, never the
       raw best Sharpe.
    9. Registry rows via ``build_experiment_records`` (``dataset_hash`` / ``config_hash``
       mandatory) under ``registry_records``; summary written to
       ``<reports_dir>/research/portfolio_<exp_id>.json``.

    ``verdict`` is PASS when any configuration passes every gate, else FAIL, and
    ``recommendation`` is the written consequence (index, or paper with the frozen
    configuration).
    """
    if profile not in ("smoke", "full"):
        raise ValueError(f"unknown profile {profile!r}: expected 'smoke' or 'full'")
    if not data:
        raise ValueError("run_portfolio_research: data is empty")
    run_id = exp_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    capital = INITIAL_EQUITY

    ref_symbol = settings.universe.benchmark if settings.universe.benchmark in data else next(iter(data))
    data_used, holdout_info = apply_holdout(settings, data, ref_symbol, exp_id=run_id, reports_dir=reports_dir)
    data_used = {sym: df for sym, df in data_used.items() if df is not None and len(df) > 0}
    if not data_used:
        raise ValueError("run_portfolio_research: no bars left after the hold-out")
    prices = close_frame(data_used)
    symbols = list(prices.columns)
    boxes = {e.symbol: e.box for e in universe.entries if e.symbol in symbols}
    years_data = _years_span(prices.index)

    candidates = portfolio_candidates(profile)
    ledger_path = (Path(reports_dir) / "research" / TRIALS_LEDGER) if reports_dir is not None else None
    prior_trials = load_trials_ledger(ledger_path)
    n_random = RANDOM_PORTFOLIOS[profile]
    # long_only → longs only; short_only → shorts only; long_short → both. (Before, short_only built a
    # long-only system that the engine's short-only direction then zeroed: no trades at all.)
    long_only = settings.trading.direction == "long_only"
    short_only = settings.trading.direction == "short_only"

    # Pass 1: run every configuration and measure its evaluated window.
    evaluated: List[Dict[str, Any]] = []
    bench_cache: Dict[pd.Timestamp, Dict[str, Any]] = {}
    for candidate_id, rules, weighting in candidates:
        smoke_kw: Dict[str, Any] = (
            {
                "scalar_min_periods": 60,
                "fdm_min_periods": 60,
                "idm_min_periods": 60,
                "box_min_periods": 40,
                "hrp_min_periods": 60,
                "vol_span": 20,
                "step": 5,
            }
            if profile == "smoke"
            else {}
        )
        cfg = SystemConfig(
            rules=tuple(rules),
            instrument_weighting=weighting,  # type: ignore[arg-type]
            boxes=boxes,
            capital=capital,
            long_only=long_only,
            short_only=short_only,
            max_leverage=1.0,
            **smoke_kw,
        )
        strategy = PipelineStrategy(cfg)
        res = backtest(
            data=data_used,
            strategy=strategy,
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
            initial_equity=capital,
            direction=settings.trading.direction,
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=capital)),
            reg_fees_cfg=settings.reg_fees,
        )
        out = strategy.last_output
        params: Dict[str, Any] = {
            "family": "pipeline",
            "rules": list(rules),
            "instrument_weighting": weighting,
            "forecast_scalar_mode": cfg.forecast_scalar_mode,
            "scalar_source": dict(out.scalar_source) if out is not None else {},
            "forecast_cap": cfg.forecast_cap,
            "fdm_max": cfg.fdm_max,
            "idm_max": cfg.idm_max,
            "tau": cfg.tau,
            "buffer_frac": cfg.buffer_frac,
            "long_only": cfg.long_only,
            "short_only": cfg.short_only,
            "max_leverage": cfg.max_leverage,
            "capital": cfg.capital,
            "symbols": symbols,
            "boxes": boxes,
            "direction": settings.trading.direction,
        }
        if smoke_kw:
            params["smoke_overrides"] = dict(smoke_kw)
        row: Dict[str, Any] = {"candidate_id": candidate_id, "params": params, "symbol": ref_symbol}
        row["trial_key"] = _trial_key(candidate_id, params)
        warmup_end = out.warmup_end if out is not None else None
        if warmup_end is None or warmup_end >= prices.index.max():
            row.update(
                {
                    "oos": {},
                    "buy_hold_oos": None,
                    "gate_passed": False,
                    "gate_reasons": ["no_warmup"],
                    "gate_checks": {"gate_mode": "strict", "no_warmup": True},
                    "benchmarks": None,
                    "random_sharpe_percentile": None,
                    "diagnostics": None,
                    "warmup_end": str(warmup_end) if warmup_end is not None else None,
                    "oos_start": None,
                    "oos_end": None,
                    "cost_drag_annual_pct": None,
                    "turnover": None,
                    "turnover_annual": None,
                    "restricted_bar_frac": None,
                }
            )
            evaluated.append({"row": row, "returns": None, "frac": None})
            continue
        oos = _window_stats(res, warmup_end, capital)
        r_bars, t_bars = restricted_counts(res, (warmup_end, prices.index.max()))
        frac = float(r_bars) / float(t_bars) if t_bars else 0.0
        oos["restricted_bar_frac"] = frac
        bench = bench_cache.get(warmup_end)
        if bench is None:
            bench = compute_benchmarks(
                prices, universe, capital=capital, n_random=n_random, seed=RANDOM_SEED, start=warmup_end
            )
            bench_cache[warmup_end] = bench
        sharpe = _finite(oos.get("sharpe"))
        sharpes = list(bench["random"]["sharpes"])
        pct = float(sharpe_percentile(sharpe, sharpes)) if (sharpe is not None and sharpes) else None
        rets = _window_returns(res, warmup_end)
        row.update(
            {
                "vol_target": vol_target_diagnostics(cfg, out, warmup_end, oos),
                "oos": oos,
                "buy_hold_oos": dict(bench["sixty_forty"]["stats"]),
                "benchmarks": _public_benchmarks(bench),
                "random_sharpe_percentile": pct,
                "diagnostics": daily_return_diagnostics(rets),
                "warmup_end": str(warmup_end),
                "oos_start": oos.get("oos_start"),
                "oos_end": oos.get("oos_end"),
                "cost_drag_annual_pct": oos.get("cost_drag_annual_pct"),
                "turnover": oos.get("turnover"),
                "turnover_annual": oos.get("turnover_annual"),
                "restricted_bar_frac": frac,
                "holdout_overused": bool(holdout_info.get("holdout_overused")),
            }
        )
        evaluated.append({"row": row, "returns": rets, "frac": frac})

    # Every configuration ever evaluated counts as a trial (cross-run ledger), not just this grid.
    keys_this_run = {str(e["row"]["trial_key"]) for e in evaluated}
    n_trials_run = len(candidates)
    n_trials = len(keys_this_run | set(prior_trials))
    trial_sharpes: List[float] = []
    for e in evaluated:
        sr_val = _finite((e["row"].get("diagnostics") or {}).get("sr_daily"))
        if sr_val is not None:
            trial_sharpes.append(sr_val)
    for key, prior in prior_trials.items():
        sr_val = _finite(prior.get("sr_daily"))
        if key not in keys_this_run and sr_val is not None:
            trial_sharpes.append(sr_val)
    pbo = pbo_block({e["row"]["candidate_id"]: e["returns"] for e in evaluated if e["returns"] is not None})
    budget_target = float(settings.research.trial_budget_target_sharpe)
    budget: Dict[str, Any] = compute_trial_budget(n_trials, years_data, target_sharpe=budget_target)
    budget["fail_on_budget_exceeded"] = bool(settings.research.fail_on_budget_exceeded)

    # Pass 2: statistical gates with the diagnostics (DSR, PBO, t-stat, percentile, hold-out).
    rows: List[Dict[str, Any]] = []
    for e in evaluated:
        row = e["row"]
        if e["returns"] is None:
            rows.append(row)
            continue
        oos = row["oos"]
        diag = dict(row["diagnostics"])
        dsr = dsr_block(diag, trial_sharpes, n_trials)
        diag["dsr"] = dsr
        diag["pbo"] = pbo
        row["diagnostics"] = diag
        # Trial budget on the evaluated window's years, not on the warm-up.
        cand_budget = compute_trial_budget(n_trials, float(oos.get("years") or 0.0), target_sharpe=budget_target)
        cand_budget["fail_on_budget_exceeded"] = bool(settings.research.fail_on_budget_exceeded)
        gate = evaluate_strict_gates(
            stitched_oos_stats=oos,
            bh_stats=row["buy_hold_oos"],
            restricted_bar_frac=float(e["frac"]),
            diagnostics={"dsr": dsr, "pbo": pbo if pbo.get("applicable") else None},
            budget=cand_budget,
            holdout=holdout_info,
        )
        extra_ok, extra_reasons, extra_checks = portfolio_extra_gates(
            diag, dsr, pbo, row["random_sharpe_percentile"], holdout_info
        )
        checks: Dict[str, Any] = dict(gate.checks)
        checks.update(extra_checks)
        checks.update({"gate_mode": "strict", "restricted_bar_frac": float(e["frac"]), "n_trials": n_trials})
        row.update(
            {
                "gate_passed": bool(gate.passed and extra_ok),
                "gate_reasons": list(gate.reasons) + extra_reasons,
                "gate_checks": checks,
                "budget": dict(cand_budget),
            }
        )
        rows.append(row)

    rows = [_noneify(r) for r in rows]
    n_pass = sum(1 for r in rows if r.get("gate_passed"))
    verdict = "PASS" if n_pass > 0 else "FAIL"
    best = _best_row(rows)
    best_id = str(best["candidate_id"]) if best else None
    if verdict == "PASS":
        recommendation = f"{RECOMMENDATION_PASS} Configuración: {best_id}."
    else:
        recommendation = RECOMMENDATION_FAIL
    if best is not None and best.get("budget"):
        budget = dict(best["budget"])

    if ledger_path is not None:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with ledger_path.open("a", encoding="utf-8") as fh:
            for r in rows:
                diag_r = r.get("diagnostics") or {}
                entry = {
                    "ts": stamp,
                    "exp_id": run_id,
                    "trial_key": r.get("trial_key"),
                    "candidate_id": r.get("candidate_id"),
                    "profile": profile,
                    "sr_daily": diag_r.get("sr_daily"),
                    "n_obs": diag_r.get("n_obs"),
                }
                fh.write(json.dumps(_noneify(entry), separators=(",", ":")) + "\n")

    summary: Dict[str, Any] = {
        "exp_id": run_id,
        "phase": PHASE,
        "profile": profile,
        "universe": universe.name,
        "symbols": symbols,
        "boxes": boxes,
        "reference_symbol": ref_symbol,
        "direction": settings.trading.direction,
        "capital": capital,
        "n_trials": n_trials,
        "n_trials_run": n_trials_run,
        "n_trials_prior": len(set(prior_trials) - keys_this_run),
        "trials_ledger": str(ledger_path) if ledger_path is not None else None,
        "n_candidates": len(rows),
        "n_pass": n_pass,
        "n_fail": len(rows) - n_pass,
        "gate_mode": "strict",
        "gates": {
            "min_t_stat": MIN_T_STAT,
            "min_dsr": 0.95,
            "pbo_max": 0.5,
            "min_random_percentile": MIN_RANDOM_PERCENTILE,
            "holdout_required": True,
        },
        "pbo": pbo,
        "selection_rule": SELECTION_RULE,
        "any_gate_passed": n_pass > 0,
        "verdict": verdict,
        "recommendation": recommendation,
        "best_candidate": best_id,
        "best_diagnostics": (best or {}).get("diagnostics"),
        "vol_target": (best or {}).get("vol_target"),
        "benchmarks": (best or {}).get("benchmarks"),
        "random_sharpe_percentile": (best or {}).get("random_sharpe_percentile"),
        "cost_drag_annual_pct": (best or {}).get("cost_drag_annual_pct"),
        "turnover": (best or {}).get("turnover"),
        "turnover_annual": (best or {}).get("turnover_annual"),
        "warmup_end": (best or {}).get("warmup_end"),
        "oos_start": (best or {}).get("oos_start"),
        "oos_end": (best or {}).get("oos_end"),
        "n_random_portfolios": n_random,
        # Research discipline (playbook phase 1): trial budget + frozen hold-out.
        "years_available": float(budget["years_available"]),
        "years_data": years_data,
        "years_needed": float(budget["years_needed"]),
        "budget_ok": bool(budget["budget_ok"]),
        "trial_budget_target_sharpe": float(budget["target_sharpe"]),
        "fail_on_budget_exceeded": bool(budget["fail_on_budget_exceeded"]),
        "budget": dict(budget),
        "holdout_start": holdout_info.get("holdout_start"),
        "holdout_applied": bool(holdout_info.get("holdout_applied")),
        "holdout_opened": bool(holdout_info.get("holdout_opened")),
        "holdout_overused": bool(holdout_info.get("holdout_overused")),
        "holdout_opening_no": holdout_info.get("holdout_opening_no"),
        "holdout_openings_log": holdout_info.get("holdout_openings_log"),
        "holdout": dict(holdout_info),
        "data_start": str(prices.index.min()),
        "data_end": str(prices.index.max()),
        "n_bars_used": int(len(prices.index)),
        "n_bars_hidden": int(holdout_info.get("n_bars_hidden") or 0),
        "candidates": rows,
        "note": (
            "Passing strict gates ≠ deploy. Stats via backtest.metrics.compute_stats on the engine "
            "equity curve from warmup_end; benchmarks on the same window; max_leverage 1.0 (engine cap). "
            "PASS also needs t ≥ 3, DSR ≥ 0.95 over every trial ever logged, PBO < 0.5, Sharpe in the top "
            "5 % of random long-only portfolios and a declared hold-out."
        ),
    }
    records = build_experiment_records(
        rows,
        exp_id=run_id,
        git_commit=git_commit(),
        dataset_hash=dataset_hash(dict(data_used)),
        config_hash=config_hash(settings),
        notes=f"{PHASE} profile={profile}",
        suite_summary=summary,
    )
    summary["registry_records"] = [_noneify(asdict(rec)) for rec in records]
    summary["dataset_hash"] = records[0].dataset_hash if records else dataset_hash(dict(data_used))
    summary["config_hash"] = records[0].config_hash if records else config_hash(settings)

    if reports_dir is not None:
        research_dir = Path(reports_dir) / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        artifact = research_dir / f"portfolio_{run_id}.json"
        artifact.write_text(
            json.dumps(_noneify(summary), ensure_ascii=False, separators=(",", ":"), indent=2),
            encoding="utf-8",
        )
        summary["artifact"] = str(artifact)
    return summary


__all__ = [
    "INITIAL_EQUITY",
    "INSTRUMENT_WEIGHTINGS",
    "PHASE",
    "RANDOM_PORTFOLIOS",
    "RECOMMENDATION_FAIL",
    "RECOMMENDATION_PASS",
    "close_frame",
    "compute_benchmarks",
    "portfolio_candidates",
    "rule_sets",
    "run_portfolio_research",
    "sixty_forty_legs",
]
