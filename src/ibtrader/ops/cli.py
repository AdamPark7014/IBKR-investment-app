from __future__ import annotations

from typing import Any, Optional, cast

import numpy as np
import pandas as _pd
import typer
from rich import print as rprint

from ..backtest.engine import backtest
from ..backtest.metrics import compute_stats
from ..backtest.report import save_equity_report
from ..config import AppSettings
from ..data.cache import load_lineage
from ..data.service import load_universe_v2
from ..diagnostics.suspicious import diagnose as diagnose_suspicious
from ..engine.decision import DecisionEngine
from ..logging import setup_logging
from ..ops.killswitch import activate_killswitch, clear_killswitch
from ..ops.status import status_summary
from ..regime.gmm import build_regime_features, fit_gmm_regime
from ..research import build_experiment_records, run_research_suite
from ..research.registry import save_experiment
from ..risk.manager import RiskManager, RiskState
from ..strategy.sma_crossover import SMACrossover
from ..validation.signal import validate_sma_signal
from ..validation.walkforward import walk_forward_sma
from .artifacts import git_commit, save_run_artifact

app = typer.Typer(no_args_is_help=True)
log = setup_logging()


def _noneify(obj: Any) -> Any:
    import math as _math

    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _noneify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_noneify(v) for v in obj]
    return obj


KNOWN_TRADING_VARS = {
    "TRADING__ALLOW_SHORT",
    "TRADING__REBALANCE_BAND_PCT",
    "TRADING__DIRECTION",
    "TRADING__BENEFIT_BPS",
    "TRADING__RISK_COST_BPS",
}


def warn_unknown_trading_env() -> None:
    import os as _os

    unknown = [k for k in _os.environ.keys() if k.startswith("TRADING__") and k not in KNOWN_TRADING_VARS]
    if unknown:
        log.warning("unknown_trading_env_vars %s", unknown)
    # Warn loudly on deprecated ALLOW_SHORT usage
    if _os.environ.get("TRADING__ALLOW_SHORT", "").strip().lower() in {"true", "1", "yes"}:
        log.warning("deprecated_trading_allow_short set=true; usa TRADING__DIRECTION=long_only|short_only|long_short")


@app.command()
def status() -> None:
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    rprint(status_summary(s))


@app.command("download-data")
def download_data() -> None:
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    # Use V2 providers pipeline with quality gate
    data = load_universe_v2(s)
    rprint({k: len(v) for k, v in data.items()})


@app.command()
def backtest_sample(
    symbol: Optional[str] = None,
    exp_id: Optional[str] = None,
    with_risk: bool = False,
    risk_on_threshold: Optional[float] = None,
) -> None:
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if s.trading.allow_short:
        log.warning(
            "deprecated_trading_allow_short config=true; usa TRADING__DIRECTION=long_only|short_only|long_short"
        )
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    # Build base strategy; direction controls exposure, not allow_short
    base_strat = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=True,
    )
    strat = _DirectionWrapper(base_strat, s.trading.direction)
    # Optional risk veto
    risk_on_series = None
    if with_risk:
        # Expanding fit per date (walk-forward regime probabilities)
        from ..regime.gmm import build_regime_features, fit_gmm_regime

        bench = s.universe.benchmark if s.universe.benchmark in data else s.universe.symbols[0]
        bench_close = data[bench]["close"].astype(float)
        feats_all = build_regime_features(bench_close)
        probs = []
        idxs = list(feats_all.index)
        for i in range(len(idxs)):
            tr_idx = idxs[: i + 1]
            if len(tr_idx) < 60:
                probs.append(0.0)
                continue
            model, _ = fit_gmm_regime(bench_close.reindex(tr_idx), n_components=2, train_slice=slice(None))
            p = model.predict_proba(feats_all.iloc[[i]])
            probs.append(float(p[0, model.risk_on_label]))
        risk_on_series = _pd.Series(probs, index=feats_all.index)
    result = backtest(
        data=data,
        strategy=strat,
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
        rebalance_band_pct=float(s.trading.rebalance_band_pct),
        benefit_bps=float(s.trading.benefit_bps),
        risk_cost_bps=float(s.trading.risk_cost_bps),
        direction=s.trading.direction,
        risk_on=risk_on_series,
        risk_on_threshold=(
            float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
        ),
        target_vol_annual=float(s.risk.target_vol_annual),
    )
    # Buy & Hold baseline on benchmark
    bench = s.universe.benchmark
    if bench in data:
        px = data[bench]["close"].astype(float).dropna()
        initial = 100_000.0
        units = initial / float(px.iloc[0])
        equity_bh = (units * px).rename("equity")
        returns_bh = equity_bh.pct_change().fillna(0.0)
        stats_bh = compute_stats(equity_bh, returns_bh)
        bh = {
            "cagr": stats_bh.cagr,
            "sharpe": stats_bh.sharpe,
            "sortino": stats_bh.sortino,
            "max_dd": stats_bh.max_drawdown,
            "win_rate": stats_bh.win_rate,
            "exposure": stats_bh.exposure,
            "calmar": stats_bh.calmar,
            "recovery_factor": stats_bh.recovery_factor,
            "current_underwater_days": stats_bh.current_underwater_days,
            "max_underwater_days": stats_bh.max_underwater_days,
            "var_95": stats_bh.var_95,
            "cvar_95": stats_bh.cvar_95,
            "trade_count": 0,
            "total_commission": 0.0,
            "turnover": 0.0,
            "win_rate_trades": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
        }
    else:
        bh = None
    from datetime import datetime as _dt

    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = save_equity_report(result, s.data.reports_dir, name=f"backtest_{run_id}")
    # Suspicious-performance diagnostics (pass lineage source)
    lineage_sources = {}
    for symb in s.universe.symbols:
        meta = load_lineage(s.data.cache_dir, symb, s.engine.bar_size)
        if meta is not None:
            lineage_sources[symb] = meta.source or ""
    susp = diagnose_suspicious(result, data, lineage_sources=lineage_sources)
    # Save run artifact
    art_path = save_run_artifact(result, s, data, s.data.reports_dir, run_id, extra={"report_html": out})
    rprint(
        {
            "report": out,
            "artifact": art_path,
            "settings": {
                "direction": s.trading.direction,
                "rebalance_band_pct": s.trading.rebalance_band_pct,
                "allow_short_deprecated": s.trading.allow_short,
                "benefit_bps": s.trading.benefit_bps,
                "risk_cost_bps": s.trading.risk_cost_bps,
            },
            "suspicious": [f"{f.code}:{f.reason}" for f in susp],
            "cagr": result.stats.cagr,
            "sharpe": result.stats.sharpe,
            "sortino": result.stats.sortino,
            "max_dd": result.stats.max_drawdown,
            "win_rate": result.stats.win_rate,
            "exposure": result.stats.exposure,
            "calmar": result.stats.calmar,
            "recovery_factor": result.stats.recovery_factor,
            "current_underwater_days": result.stats.current_underwater_days,
            "max_underwater_days": result.stats.max_underwater_days,
            "var_95": result.stats.var_95,
            "cvar_95": result.stats.cvar_95,
            "trade_count": result.stats.trade_count,
            "total_commission": result.stats.total_commission,
            "turnover": result.stats.turnover,
            "win_rate_trades": result.stats.win_rate_trades,
            "pnl_win_share": (
                result.stats.profit_factor / (1 + result.stats.profit_factor) if result.stats.profit_factor > 0 else 0.0
            ),
            "profit_factor": result.stats.profit_factor,
            "expectancy": result.stats.expectancy,
            "buy_hold": bh,
        }
    )


class _DirectionWrapper(SMACrossover):
    def __init__(self, base: SMACrossover, mode: str) -> None:
        super().__init__(fast_window=base.fast, slow_window=base.slow, allow_short=True)
        self.mode = mode

    def generate_signals(self, data):
        sigs = super().generate_signals(data)
        if self.mode == "long_only":
            return {k: v.clip(lower=0) for k, v in sigs.items()}
        if self.mode == "short_only":
            return {k: (v.mask(v > 0, 0)).clip(upper=0) for k, v in sigs.items()}
        return sigs


@app.command("compare-directions")
def compare_directions(symbol: Optional[str] = None, exp_id: Optional[str] = None) -> None:
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if s.trading.allow_short:
        log.warning(
            "deprecated_trading_allow_short config=true; usa TRADING__DIRECTION=long_only|short_only|long_short"
        )
    if symbol:
        s.universe.symbols = [symbol]
    # Use V2 providers pipeline with quality gate
    data = load_universe_v2(s)
    base = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=True,
    )
    modes = ["long_only", "short_only", "long_short"]
    results = {}
    for m in modes:
        strat = _DirectionWrapper(base, m)
        # Optional simple risk veto via flag env COMPARE_WITH_RISK (expanding WFO labeling)
        import os

        with_risk = os.environ.get("COMPARE_WITH_RISK", "").strip().lower() in {"1", "true", "yes"}
        risk_on_series = None
        rot = float(s.risk.risk_on_threshold)
        if with_risk:
            from ..regime.gmm import build_regime_features, fit_gmm_regime

            bench = s.universe.benchmark if s.universe.benchmark in data else s.universe.symbols[0]
            bench_close = data[bench]["close"].astype(float)
            feats_all = build_regime_features(bench_close)
            # Expanding fit per date (walk-forward regime probabilities)
            probs = []
            idxs = list(feats_all.index)
            for i in range(len(idxs)):
                tr_idx = idxs[: i + 1]
                if len(tr_idx) < 60:
                    probs.append(0.0)
                    continue
                model, _ = fit_gmm_regime(bench_close.reindex(tr_idx), n_components=2, train_slice=slice(None))
                p = model.predict_proba(feats_all.iloc[[i]])
                probs.append(float(p[0, model.risk_on_label]))
            risk_on_series = _pd.Series(probs, index=feats_all.index)
        res = backtest(
            data=data,
            strategy=strat,
            commission_cfg=s.commission,
            slippage_cfg=s.slippage,
            rebalance_band_pct=float(s.trading.rebalance_band_pct),
            benefit_bps=float(s.trading.benefit_bps),
            risk_cost_bps=float(s.trading.risk_cost_bps),
            direction=m,
            risk_on=risk_on_series,
            risk_on_threshold=rot,
            target_vol_annual=float(s.risk.target_vol_annual),
        )
        results[m] = {
            "cagr": res.stats.cagr,
            "sharpe": res.stats.sharpe,
            "sortino": res.stats.sortino,
            "calmar": res.stats.calmar,
            "max_dd": res.stats.max_drawdown,
            "win_rate": res.stats.win_rate,
            "exposure": res.stats.exposure,
            "recovery_factor": res.stats.recovery_factor,
            "current_underwater_days": res.stats.current_underwater_days,
            "max_underwater_days": res.stats.max_underwater_days,
            "var_95": res.stats.var_95,
            "cvar_95": res.stats.cvar_95,
            "trade_count": res.stats.trade_count,
            "total_commission": res.stats.total_commission,
            "turnover": res.stats.turnover,
            "win_rate_trades": res.stats.win_rate_trades,
            "profit_factor": res.stats.profit_factor,
            "expectancy": res.stats.expectancy,
        }
    # Buy & Hold
    bench = s.universe.benchmark
    bh = None
    if bench in data:
        px = data[bench]["close"].astype(float).dropna()
        initial = 100_000.0
        units = initial / float(px.iloc[0])
        equity_bh = (units * px).rename("equity")
        returns_bh = equity_bh.pct_change().fillna(0.0)
        stats_bh = compute_stats(equity_bh, returns_bh)
        # Full extended metric set for Buy & Hold
        bh = {
            "cagr": stats_bh.cagr,
            "sharpe": stats_bh.sharpe,
            "sortino": stats_bh.sortino,
            "max_dd": stats_bh.max_drawdown,
            "win_rate": stats_bh.win_rate,
            "exposure": stats_bh.exposure,
            "calmar": stats_bh.calmar,
            "recovery_factor": stats_bh.recovery_factor,
            "current_underwater_days": stats_bh.current_underwater_days,
            "max_underwater_days": stats_bh.max_underwater_days,
            "var_95": stats_bh.var_95,
            "cvar_95": stats_bh.cvar_95,
            "trade_count": 0,
            "total_commission": 0.0,
            "turnover": 0.0,
            "win_rate_trades": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
        }
    rprint(
        {
            "settings": {"rebalance_band_pct": s.trading.rebalance_band_pct},
            "directions": results,
            "buy_hold": bh,
        }
    )


@app.command("paper-run")
def paper_run() -> None:
    s = AppSettings()
    s.resolve_paths()
    data = load_universe_v2(s)
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    # Fase 1: sólo imprimir/registrar (NO_TRADE)
    rprint([d.__dict__ for d in decisions])


@app.command()
def kill() -> None:
    s = AppSettings()
    s.resolve_paths()
    activate_killswitch(s.risk.killswitch_file)
    rprint({"kill_switch": True})


@app.command("clear-kill")
def clear_kill() -> None:
    s = AppSettings()
    s.resolve_paths()
    clear_killswitch(s.risk.killswitch_file)
    rprint({"kill_switch": False})


@app.command("regime-fit")
def regime_fit(symbol: Optional[str] = None, n_components: int = 2, exp_id: Optional[str] = None) -> None:
    """
    P6 Regime Engine: learned regimes via GaussianMixture on benchmark returns/volatility.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    bench = s.universe.benchmark if s.universe.benchmark in data else next(iter(data.keys()))
    model, rep = fit_gmm_regime(data[bench]["close"], n_components=n_components)
    from datetime import datetime as _dt

    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    # Save CSV report
    import os

    out_csv = os.path.join(s.data.reports_dir, f"regime_{run_id}.csv")
    rep.to_csv(out_csv, index=True)
    # Summary
    counts = rep["regime"].value_counts().to_dict()
    cols = [c for c in ["ret_1d", "vol_20"] if c in rep.columns]
    means = rep.groupby("regime")[cols].mean().to_dict() if cols else {}
    rprint(
        {
            "report": out_csv,
            "components": n_components,
            "counts": counts,
            "means": means,
        }
    )


@app.command("signal-validate")
def signal_validate(
    symbol: Optional[str] = None,
    direction: str = "long_only",
    exp_id: Optional[str] = None,
) -> None:
    """
    P7 Signal Validation: CV evaluation of SMA signal against forward returns.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    folds, agg = validate_sma_signal(
        data,
        sym,
        fast=int(s.strategy.params.get("fast_window", 10)),
        slow=int(s.strategy.params.get("slow_window", 30)),
        direction=direction,
    )
    # Buy & Hold for comparison
    px = data[s.universe.benchmark]["close"].astype(float)
    eq = (100_000.0 / float(px.iloc[0])) * px
    bh_ret = eq.pct_change().fillna(0.0)
    ann = np.sqrt(252.0)
    bh_stats = {
        "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (252 / max(len(eq), 1)) - 1.0),
        "sharpe": float((bh_ret.mean() / (bh_ret.std(ddof=0) or 1e-9)) * ann),
        "max_dd": float((eq / eq.cummax() - 1.0).min()),
    }
    rprint(
        {
            "symbol": sym,
            "direction": direction,
            "cv": [{"mean": f.mean_ret, "sharpe": f.sharpe, "n": f.n_obs} for f in folds],
            "cv_aggregate": {"mean": agg.mean_ret, "sharpe": agg.sharpe, "n": agg.n_obs},
            "buy_hold": bh_stats,
        }
    )


@app.command("run-with-risk")
def run_with_risk(
    symbol: Optional[str] = None,
    exp_id: Optional[str] = None,
    risk_on_threshold: Optional[float] = None,
) -> None:
    """
    P8 Risk Integration: regime veto + volatility-target sizing. No live orders; prints decision.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    # Historical regime probabilities (expanding, min window)
    bench = s.universe.benchmark if s.universe.benchmark in data else sym
    bench_close = data[bench]["close"].astype(float)
    feats_all = build_regime_features(bench_close)
    min_train = 60
    probs = []
    idxs = list(feats_all.index)
    for i in range(len(idxs)):
        tr_idx = idxs[: i + 1]
        if len(tr_idx) < min_train:
            probs.append(0.0)
            continue
        model, _ = fit_gmm_regime(bench_close.reindex(tr_idx), n_components=2, train_slice=slice(None))
        p = model.predict_proba(feats_all.iloc[[i]])
        probs.append(float(p[0, model.risk_on_label]))
    risk_on_series = _pd.Series(probs, index=feats_all.index)
    # Strategy with risk veto + vol-target sizing backtest
    strat = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=True,
    )
    from ..backtest.engine import backtest as _bt

    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
    res = _bt(
        data=data,
        strategy=strat,
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
        direction=s.trading.direction,
        risk_on=risk_on_series,
        risk_on_threshold=thr,
        target_vol_annual=float(s.risk.target_vol_annual),
        risk_manager=RiskManager(s.risk, RiskState(starting_equity_today=100_000.0)),
    )
    # Save artifact
    from datetime import datetime as _dt

    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    art_path = save_run_artifact(
        res,
        s,
        data,
        s.data.reports_dir,
        f"risk_{run_id}",
        extra={"risk_on_threshold": thr},
    )
    # Suspicious diagnostics
    lineage_sources = {}
    for symb in s.universe.symbols:
        meta = load_lineage(s.data.cache_dir, symb, s.engine.bar_size)
        if meta is not None:
            lineage_sources[symb] = meta.source or ""
    susp = diagnose_suspicious(res, data, lineage_sources=lineage_sources)
    rprint(
        {
            "symbol": sym,
            "risk_on_threshold": thr,
            "metrics": {
                "cagr": res.stats.cagr,
                "sharpe": res.stats.sharpe,
                "sortino": res.stats.sortino,
                "max_dd": res.stats.max_drawdown,
                "trade_count": res.stats.trade_count,
                "fees": res.stats.total_commission,
            },
            "suspicious": [f"{f.code}:{f.reason}" for f in susp],
            "artifact": art_path,
        }
    )


@app.command("walk-forward")
def walk_forward(exp_id: Optional[str] = None) -> None:
    """
    P9 Walk Forward: train/validate/test by time with frozen params; OOS never used for tuning.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    wf, summary = walk_forward_sma(s, data, sym, direction=s.trading.direction)
    # Save stitched OOS artifact from the last fold's params applied to the last test span equity (already in wf/test)
    from datetime import datetime as _dt

    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    # Build a BacktestResult-compatible object from stitched OOS series and trades across folds
    # imports moved to module scope to satisfy linting
    # Stitched OOS equity curve
    eq_pairs = summary.get("stitched_oos_equity") or []
    eq_series = (
        _pd.Series({_pd.Timestamp(t): v for t, v in eq_pairs}).sort_index() if eq_pairs else _pd.Series(dtype=float)
    )
    # Concatenate OOS trades across folds (already carry reason)
    oos_trades: list[tuple[str, str, int, float, str]] = []
    for fd in summary.get("folds", []) or []:
        for tr in fd.get("oos_trades", []):
            oos_trades.append(
                (
                    str(tr["date"]),
                    str(tr["symbol"]),
                    int(tr["qty"]),
                    float(tr["price"]),
                    str(tr.get("reason", "signal")),
                )
            )
    # Compute stitched stats if available
    if len(eq_series) > 1:
        rets = eq_series.pct_change().fillna(0.0)
        stats_obj = compute_stats(eq_series, rets)
        trade_count = int(summary.get("oos_total_trades", 0) or 0)
        total_commission = float(summary.get("oos_commission_approx", 0.0) or 0.0)
        stats_obj.trade_count = trade_count
        stats_obj.total_commission = total_commission
    else:
        from ..backtest.metrics import PerformanceStats as _PS

        _nan = float("nan")
        stats_obj = _PS(
            cagr=_nan,
            sharpe=_nan,
            sortino=_nan,
            max_drawdown=_nan,
            win_rate=_nan,
            exposure=_nan,
            total_return=_nan,
            volatility=_nan,
            trade_count=int(summary.get("oos_total_trades") or 0),
            total_commission=float(summary.get("oos_commission_approx") or 0.0),
            turnover=_nan,
            win_rate_trades=_nan,
            profit_factor=_nan,
            expectancy=_nan,
            calmar=_nan,
            recovery_factor=_nan,
            var_95=_nan,
            cvar_95=_nan,
            current_underwater_days=0,
            max_underwater_days=0,
        )

    class _BTResObj:
        def __init__(self) -> None:
            self.equity_curve = eq_series
            self.returns = eq_series.pct_change().fillna(0.0)
            from pandas import Series as _Series

            self.positions: dict[str, _Series] = {}
            self.trades: list[tuple[str, str, int, float, str]] = oos_trades
            self.stats = stats_obj

    from ..backtest.engine import BacktestResult as _BTRes

    _mini = _BTResObj()
    # Strategy version override reflects multi-fold chosen params
    chosen_params = [
        {"fast": fd["chosen_params"]["fast"], "slow": fd["chosen_params"]["slow"]} for fd in summary.get("folds", [])
    ]
    extra = {
        "walk_forward": summary,
        "per_fold_params": chosen_params,
        "strategy_version_override": "sma_wf_multi",
    }
    art_path = save_run_artifact(
        cast(_BTRes, _mini),
        s,
        data,
        s.data.reports_dir,
        f"wf_{run_id}",
        extra=extra,
    )
    # Suspicious diagnostics using stitched series
    lineage_sources = {}
    for symb in s.universe.symbols:
        meta = load_lineage(s.data.cache_dir, symb, s.engine.bar_size)
        if meta is not None:
            lineage_sources[symb] = meta.source or ""
    susp = diagnose_suspicious(cast(_BTRes, _mini), data, lineage_sources=lineage_sources)
    # Build payload as JSON with None for undefined values and include strategy_version from chosen params
    import json as _json

    payload = {
        "symbol": sym,
        # Never present a single fold as 'the' best; picks live under per_fold_params / folds
        "best_params": None,
        "per_fold_params": summary.get("per_fold_params"),
        "in_sample": None,
        "validation": None,
        "oos": {
            **(wf.stitched_oos or {}),
            "commission": summary.get("oos_commission_approx"),
            "total_commission": summary.get("oos_commission_approx"),
        },
        "buy_hold_oos": summary.get("buy_hold_oos"),
        "folds": summary.get("folds"),
        "oos_total_trades": summary.get("oos_total_trades"),
        "oos_commission_approx": summary.get("oos_commission_approx"),
        "tried_param_count": summary.get("tried_param_count"),
        "suspicious": [f"{f.code}:{f.reason}" for f in susp],
        "artifact": art_path,
    }
    typer.echo(_json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":")))


@app.command("research-run")
def research_run(exp_id: Optional[str] = None) -> None:
    """
    V3 research suite: SMA/regime/cost/TSMOM/mean-rev/multi-asset gated tracks
    plus embargo, PBO, CPCV, DSR, turnover diagnostics and an honest report.
    Does not change production strategy defaults. Most candidates are expected to FAIL gates.
    """
    import json as _json
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    from ..research.multi_asset import DEFAULT_RESEARCH_SYMBOLS

    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    # Expand single-name default to the research ETF cross-section.
    if list(s.universe.symbols) == ["SPY"]:
        s.universe.symbols = list(DEFAULT_RESEARCH_SYMBOLS)
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    suite = run_research_suite(
        s,
        data,
        sym,
        direction=s.trading.direction,
        n_folds=3,
    )
    results = list(suite.get("candidates") or [])
    research_dir = _Path(s.data.reports_dir) / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    registry_path = research_dir / f"experiments_{run_id}.jsonl"
    records = build_experiment_records(results, exp_id=run_id, git_commit=git_commit())
    for rec in records:
        save_experiment(registry_path, rec)
    n_pass = int(suite.get("n_pass") or 0)
    n_fail = int(suite.get("n_fail") or 0)
    suite_label = "sma+regime+cost_ladder+tsmom+mean_reversion+embargo+pbo+" "multi_asset+cpcv+dsr+turnover"
    payload = {
        "exp_id": run_id,
        "symbol": sym,
        "symbols": list(s.universe.symbols),
        "phase": "V3-research",
        "suite": suite_label,
        "n_candidates": int(suite.get("n_candidates") or len(results)),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "cost_fragility": suite.get("cost_fragility"),
        "embargo_sensitivity": suite.get("embargo_sensitivity"),
        "pbo": suite.get("pbo"),
        "cross_section": suite.get("cross_section"),
        "cpcv": suite.get("cpcv"),
        "dsr": suite.get("dsr"),
        "turnover": suite.get("turnover"),
        "honest_report": suite.get("honest_report"),
        "tracks": {
            k: [
                {
                    "candidate_id": r["candidate_id"],
                    "params": r["params"],
                    "gate": "PASS" if r.get("gate_passed") else "FAIL",
                    "gate_reasons": r.get("gate_reasons") or [],
                    "oos": r.get("oos"),
                }
                for r in (suite.get("tracks") or {}).get(k) or []
            ]
            for k in (
                "sma_grid",
                "sma_regime",
                "cost_ladder",
                "tsmom",
                "mean_reversion",
                "multi_asset",
            )
        },
        "candidates": [
            {
                "candidate_id": r["candidate_id"],
                "params": r["params"],
                "oos": r["oos"],
                "buy_hold_oos": r.get("buy_hold_oos"),
                "gate": "PASS" if r.get("gate_passed") else "FAIL",
                "gate_passed": bool(r.get("gate_passed")),
                "gate_detail": {
                    "checks": r.get("gate_checks") or {},
                    "reasons": r.get("gate_reasons") or [],
                },
                "gate_reasons": r.get("gate_reasons") or [],
                "oos_total_trades": r.get("oos_total_trades"),
                "oos_commission_approx": r.get("oos_commission_approx"),
            }
            for r in results
        ],
        "registry": str(registry_path),
        "any_gate_passed": bool(suite.get("any_gate_passed")),
        "note": (
            "Passing gates ≠ deploy. Failing gates / cost fragility is the normal "
            "institutional outcome. See docs/research/INSTITUTIONAL_SYSTEMATIC_STACK.md"
        ),
    }
    summary_path = research_dir / f"research_{run_id}.json"
    summary_path.write_text(
        _json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":"), indent=2),
        encoding="utf-8",
    )
    payload["artifact"] = str(summary_path)
    payload["summary_artifact"] = str(summary_path)
    typer.echo(_json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    app()
