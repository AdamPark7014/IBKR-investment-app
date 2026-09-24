from __future__ import annotations

from typing import Optional

import typer
from rich import print as rprint
import numpy as np

from ..backtest.engine import backtest
from ..backtest.metrics import compute_stats
from ..backtest.report import save_equity_report
from ..config import AppSettings
from ..data.downloader import load_universe_data  # legacy
from ..data.service import load_universe_v2
from ..engine.decision import DecisionEngine
from ..logging import setup_logging
from ..ops.killswitch import activate_killswitch, clear_killswitch
from ..ops.status import status_summary
from ..strategy.sma_crossover import SMACrossover
from ..regime.gmm import fit_gmm_regime, build_regime_features
from ..validation.signal import validate_sma_signal
from ..ml.cv import PurgedTimeSeriesSplit
from ..risk.sizing import volatility_target_weight
from ..validation.walkforward import walk_forward_sma

app = typer.Typer(no_args_is_help=True)
log = setup_logging()

KNOWN_TRADING_VARS = {
    "TRADING__ALLOW_SHORT",
    "TRADING__REBALANCE_BAND_PCT",
    "TRADING__DIRECTION",
    "TRADING__BENEFIT_BPS",
    "TRADING__RISK_COST_BPS",
}

def warn_unknown_trading_env() -> None:
    import os as _os

    unknown = [
        k for k in _os.environ.keys() if k.startswith("TRADING__") and k not in KNOWN_TRADING_VARS
    ]
    if unknown:
        log.warning("unknown_trading_env_vars %s", unknown)
    # Warn loudly on deprecated ALLOW_SHORT usage
    if _os.environ.get("TRADING__ALLOW_SHORT", "").strip().lower() in {"true", "1", "yes"}:
        log.warning(
            "deprecated_trading_allow_short set=true; usa TRADING__DIRECTION=long_only|short_only|long_short"
        )


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
def backtest_sample(symbol: Optional[str] = None, exp_id: Optional[str] = None, with_risk: bool = False, risk_on_threshold: Optional[float] = None) -> None:
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
        from ..regime.gmm import fit_gmm_regime, build_regime_features
        bench = s.universe.benchmark if s.universe.benchmark in data else s.universe.symbols[0]
        model, _ = fit_gmm_regime(data[bench]["close"], n_components=2)
        feats = build_regime_features(data[bench]["close"])
        import numpy as _np
        proba = model.predict_proba(feats)
        risk_on_series = feats.index.to_series().map(lambda d: float(proba[list(feats.index).index(d), model.risk_on_label]) if d in feats.index else 1.0)
        risk_on_series.index = feats.index
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
        risk_on_threshold=float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold),
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
    # BacktestSkeptic flags
    skeptic_flags = []
    if result.stats.cagr > 1.0:
        skeptic_flags.append("CAGR>100%")
    if result.stats.sharpe > 3.0:
        skeptic_flags.append("Sharpe>3")
    rprint(
        {
            "report": out,
            "settings": {
                "direction": s.trading.direction,
                "rebalance_band_pct": s.trading.rebalance_band_pct,
                "allow_short_deprecated": s.trading.allow_short,
                "benefit_bps": s.trading.benefit_bps,
                "risk_cost_bps": s.trading.risk_cost_bps,
            },
            "skeptic_flags": skeptic_flags,
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
                result.stats.profit_factor / (1 + result.stats.profit_factor)
                if result.stats.profit_factor > 0
                else 0.0
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
            from ..regime.gmm import fit_gmm_regime, build_regime_features
            bench = s.universe.benchmark if s.universe.benchmark in data else s.universe.symbols[0]
            bench_close = data[bench]["close"].astype(float)
            feats_all = build_regime_features(bench_close)
            # Expanding fit per date (walk-forward regime probabilities)
            probs = []
            idxs = list(feats_all.index)
            for i in range(len(idxs)):
                tr_idx = idxs[: i + 1]
                model, _ = fit_gmm_regime(bench_close.reindex(tr_idx), n_components=2, train_slice=slice(None))
                p = model.predict_proba(feats_all.iloc[[i]])
                probs.append(float(p[0, model.risk_on_label]))
            import pandas as _pd
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
    feats = build_regime_features(data[bench]["close"])
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
def run_with_risk(symbol: Optional[str] = None, exp_id: Optional[str] = None, risk_on_threshold: Optional[float] = None) -> None:
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
    # Regime model on benchmark
    bench = s.universe.benchmark if s.universe.benchmark in data else sym
    model, rep = fit_gmm_regime(data[bench]["close"], n_components=2)
    # Risk-on probability at last point using training-based label ordering
    feats = build_regime_features(data[bench]["close"])
    proba = model.predict_proba(feats.tail(1))
    p_risk_on = float(proba[0, model.risk_on_label]) if proba.shape[0] == 1 else 0.0
    # EV proxy from SMA signal
    base = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=True,
    )
    sig = base.generate_signals({sym: data[sym]})[sym].reindex(data[sym].index).fillna(0)
    last_sig = int(sig.iloc[-1]) if len(sig) else 0
    # Respect direction default
    if s.trading.direction == "long_only":
        last_sig = max(last_sig, 0)
    elif s.trading.direction == "short_only":
        last_sig = min(last_sig, 0)
    # Risk veto
    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
    veto_reason = None
    action = "ABSTAIN"
    size_pct = 0.0
    if last_sig == 0:
        veto_reason = "No signal"
    elif p_risk_on < thr:
        veto_reason = f"Risk-on prob {p_risk_on:.2f} < threshold {thr:.2f}"
    else:
        # Volatility-target sizing
        rets = data[sym]["close"].astype(float).pct_change().fillna(0.0)
        w = volatility_target_weight(rets, target_vol_annual=float(s.risk.target_vol_annual))
        size_pct = min(100.0 * w, float(s.risk.max_position_pct))
        action = "TRADE"
    rprint(
        {
            "symbol": sym,
            "signal": last_sig,
            "p_risk_on": p_risk_on,
            "threshold": thr,
            "action": action,
            "size_pct": size_pct,
            "veto_reason": veto_reason,
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
    rprint(
        {
            "symbol": sym,
            "best_params": {"fast": wf.params[0], "slow": wf.params[1]},
            "in_sample": wf.train_stats,
            "validation": wf.val_stats,
            "oos": wf.test_stats,
            "buy_hold_oos": summary.get("buy_hold_oos"),
            "folds": summary.get("folds"),
            "oos_total_trades": summary.get("oos_total_trades"),
            "tried_param_count": summary.get("tried_param_count"),
        }
    )

if __name__ == "__main__":
    app()

