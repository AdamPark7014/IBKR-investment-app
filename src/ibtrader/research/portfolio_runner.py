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

import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

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
from .gates import compute_trial_budget, evaluate_strict_gates
from .runner import build_experiment_records
from .suite import apply_holdout

Profile = Literal["smoke", "full"]

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

INSTRUMENT_WEIGHTINGS: Tuple[str, ...] = ("box_inverse_vol", "hrp", "equal")


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

    * ``smoke``: one configuration (``DEFAULT_RULES`` × ``box_inverse_vol``).
    * ``full``: small grid rules (default | ewmac only | tsmom only) × weighting
      (box_inverse_vol | hrp | equal). Every configuration counts as one trial.
    """
    if profile == "smoke":
        return [("pipeline_default_box_inverse_vol", tuple(DEFAULT_RULES), "box_inverse_vol")]
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


def _benchmark_block(name: str, returns: pd.Series, capital: float, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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


def compute_benchmarks(
    prices: pd.DataFrame,
    universe: Optional[UniverseSpec],
    capital: float = INITIAL_EQUITY,
    n_random: int = RANDOM_PORTFOLIOS["smoke"],
    seed: int = RANDOM_SEED,
) -> Dict[str, Any]:
    """60/40, static All Weather and random long-only portfolios over ``prices`` (one window).

    Returns ``{"sixty_forty", "all_weather", "random"}``; ``random["sharpes"]`` keeps the
    full distribution for ``sharpe_percentile`` (dropped from the written summary).
    A benchmark whose inputs are missing (e.g. All Weather without its ETFs) is reported
    as ``None`` with ``*_error`` instead of silently substituted.
    """
    equity_leg, bond_leg = sixty_forty_legs(list(prices.columns), universe)
    out: Dict[str, Any] = {}
    sf = sixty_forty(prices, equity=equity_leg, bonds=bond_leg, rebalance=BENCHMARK_REBALANCE, cost_bps=BENCHMARK_COST_BPS)
    out["sixty_forty"] = _benchmark_block(
        "sixty_forty", sf, capital, {"equity": equity_leg, "bonds": bond_leg, "rebalance": BENCHMARK_REBALANCE}
    )
    try:
        aw = all_weather_static(prices, rebalance=BENCHMARK_REBALANCE, cost_bps=BENCHMARK_COST_BPS)
        out["all_weather"] = _benchmark_block("all_weather", aw, capital, {"rebalance": BENCHMARK_REBALANCE})
    except Exception as exc:
        out["all_weather"] = None
        out["all_weather_error"] = f"{type(exc).__name__}: {exc}"
    rnd = random_long_only_portfolios(prices, n=int(n_random), seed=int(seed), rebalance=BENCHMARK_REBALANCE, cost_bps=BENCHMARK_COST_BPS)
    sharpes = _random_sharpes(rnd)
    s = pd.Series(sharpes, dtype=float)
    out["random"] = {
        "n": int(n_random),
        "n_valid": int(len(sharpes)),
        "seed": int(seed),
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
    stats.update(
        {
            "trade_count": int(len(trades_in)),
            "turnover": float(turnover),
            "turnover_annual": float(turnover / years) if years > 0 else 0.0,
            "total_costs": total_costs,
            "total_commission": float(getattr(res.stats, "total_commission", 0.0) or 0.0),
            "avg_cost_bps_per_order": float(getattr(res.stats, "avg_cost_bps_per_order", 0.0) or 0.0),
            "cost_drag_annual_pct": float(total_costs / capital / years * 100.0) if (capital and years > 0) else 0.0,
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


def _best_row(rows: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    passed = [r for r in rows if r.get("gate_passed")]
    pool = passed or [r for r in rows if _finite((r.get("oos") or {}).get("sharpe")) is not None]
    if not pool:
        return rows[0] if rows else None
    return max(pool, key=lambda r: _finite((r.get("oos") or {}).get("sharpe")) or float("-inf"))


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
       ``long_only`` from ``settings.trading.direction``.
    3. ``backtest`` with ``PipelineStrategy`` and the commission / slippage / reg-fee /
       risk settings (RiskManager on, no regime veto: the pipeline has its own sizing).
    4. OOS window = ``[warmup_end, last bar]``; ``warmup_end is None`` → FAIL ``no_warmup``.
    5. Benchmarks on the same window (``compute_benchmarks``); ``bh_stats`` for the
       gates = the 60/40 stats; ``restricted_bar_frac`` from ``restricted_counts``.
    6. ``evaluate_strict_gates`` with the trial budget (``n_trials`` = configurations
       run, ``years_available`` = span of the data used) and the hold-out block.
    7. Registry rows via ``build_experiment_records`` (``dataset_hash`` / ``config_hash``
       mandatory) under ``registry_records``; summary written to
       ``<reports_dir>/research/portfolio_<exp_id>.json``.

    ``verdict`` is PASS when any configuration passes the strict gates, else FAIL, and
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
    years_available = _years_span(prices.index)

    candidates = portfolio_candidates(profile)
    n_trials = len(candidates)
    budget = compute_trial_budget(
        n_trials, years_available, target_sharpe=float(settings.research.trial_budget_target_sharpe)
    )
    budget["fail_on_budget_exceeded"] = bool(settings.research.fail_on_budget_exceeded)
    n_random = RANDOM_PORTFOLIOS[profile]
    long_only = settings.trading.direction != "long_short"

    rows: List[Dict[str, Any]] = []
    bench_cache: Dict[pd.Timestamp, Dict[str, Any]] = {}
    for candidate_id, rules, weighting in candidates:
        cfg = SystemConfig(
            rules=tuple(rules),
            instrument_weighting=weighting,  # type: ignore[arg-type]
            boxes=boxes,
            capital=capital,
            long_only=long_only,
            max_leverage=1.0,
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
            "max_leverage": cfg.max_leverage,
            "capital": cfg.capital,
            "symbols": symbols,
            "boxes": boxes,
            "direction": settings.trading.direction,
        }
        row: Dict[str, Any] = {"candidate_id": candidate_id, "params": params, "symbol": ref_symbol}
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
                    "warmup_end": str(warmup_end) if warmup_end is not None else None,
                    "oos_start": None,
                    "oos_end": None,
                    "cost_drag_annual_pct": None,
                    "turnover": None,
                    "turnover_annual": None,
                    "restricted_bar_frac": None,
                }
            )
            rows.append(row)
            continue
        oos = _window_stats(res, warmup_end, capital)
        r_bars, t_bars = restricted_counts(res, (warmup_end, prices.index.max()))
        frac = float(r_bars) / float(t_bars) if t_bars else 0.0
        oos["restricted_bar_frac"] = frac
        bench = bench_cache.get(warmup_end)
        if bench is None:
            bench = compute_benchmarks(prices.loc[warmup_end:], universe, capital=capital, n_random=n_random, seed=RANDOM_SEED)
            bench_cache[warmup_end] = bench
        bh_stats = dict(bench["sixty_forty"]["stats"])
        gate = evaluate_strict_gates(
            stitched_oos_stats=oos,
            bh_stats=bh_stats,
            restricted_bar_frac=frac,
            diagnostics=None,
            budget=budget,
            holdout=holdout_info,
        )
        sharpe = _finite(oos.get("sharpe"))
        sharpes = list(bench["random"]["sharpes"])
        pct = float(sharpe_percentile(sharpe, sharpes)) if (sharpe is not None and sharpes) else None
        checks: Dict[str, Any] = dict(gate.checks)
        checks.update(
            {
                "gate_mode": "strict",
                "restricted_bar_frac": frac,
                "restricted_bars": int(r_bars),
                "total_bars": int(t_bars),
                "random_sharpe_percentile": pct,
            }
        )
        row.update(
            {
                "oos": oos,
                "buy_hold_oos": bh_stats,
                "gate_passed": bool(gate.passed),
                "gate_reasons": list(gate.reasons),
                "gate_checks": checks,
                "benchmarks": _public_benchmarks(bench),
                "random_sharpe_percentile": pct,
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
        "n_candidates": len(rows),
        "n_pass": n_pass,
        "n_fail": len(rows) - n_pass,
        "gate_mode": "strict",
        "any_gate_passed": n_pass > 0,
        "verdict": verdict,
        "recommendation": recommendation,
        "best_candidate": best_id,
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
        "years_available": years_available,
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
            "equity curve from warmup_end; benchmarks on the same window; max_leverage 1.0 (engine cap)."
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
