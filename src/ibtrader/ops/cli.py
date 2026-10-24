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
from ..data.providers import FixtureProvider
from ..data.service import load_universe_v2
from ..diagnostics.suspicious import diagnose as diagnose_suspicious
from ..engine.decision import DecisionEngine
from ..logging import setup_logging
from ..ops.killswitch import activate_killswitch, clear_killswitch
from ..ops.status import status_summary
from ..regime.gmm import build_regime_features, fit_gmm_regime
from ..research import build_experiment_records, run_research_suite
from ..research.registry import save_experiment
from ..research.suite import count_holdout_openings, holdout_openings_path
from ..risk.manager import RiskManager, RiskState
from ..strategy.base import Strategy
from ..strategy.mean_reversion import MeanReversion
from ..strategy.rotation import CrossSectionalMomentum
from ..strategy.sma_crossover import SMACrossover
from ..strategy.tsmom import TimeSeriesMomentum
from ..validation.signal import validate_sma_signal
from ..validation.walkforward import walk_forward_sma
from .artifacts import config_hash, dataset_hash, git_commit, save_run_artifact

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
def paper_run(
    shadow: bool = typer.Option(
        False,
        "--shadow",
        help="Log desired vs held weights via shadow book (no broker orders).",
    ),
) -> None:
    s = AppSettings()
    s.resolve_paths()
    data = load_universe_v2(s)
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    counts: dict[str, int] = {}
    for d in decisions:
        counts[d.action] = counts.get(d.action, 0) + 1
    out: dict[str, Any] = {
        "orders_sent": 0,
        "counts": counts,
        "decisions": [d.__dict__ for d in decisions],
    }
    if shadow:
        import json as _json
        from pathlib import Path as _Path

        from .shadow import desired_from_decisions, log_shadow_snapshot

        held: dict[str, float] = {}
        held_path = _Path(s.data.data_dir) / "paper_positions.json"
        if held_path.exists():
            raw = _json.loads(held_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                held = {str(k): float(v) for k, v in raw.items()}
        out["shadow"] = log_shadow_snapshot(desired_from_decisions(decisions), held=held)
        out["shadow_held_source"] = str(held_path) if held_path.exists() else None
    rprint(out)


@app.command("autopilot")
def autopilot(
    use_ai: bool = typer.Option(
        False,
        "--use-ai/--no-ai",
        help="Optional low-token brief via puerta IA (needs ANTHROPIC_*). Default: deterministic.",
    ),
    open_ui: bool = typer.Option(
        False,
        "--open/--no-open",
        help="Open the one-screen HTML in the browser.",
    ),
    language: str = typer.Option("es", "--lang", help="Brief language for PromptPack."),
    max_tokens: int = typer.Option(400, "--max-tokens", help="AI max_tokens (low-token by design)."),
) -> None:
    """Run heavy backend triage + one-screen UI. Zero broker orders."""
    import json as _json

    from ..intelligence.prompt_pack import default_pack
    from .autopilot import run_autopilot

    pack = default_pack(language=language, max_tokens=max_tokens)
    payload = run_autopilot(use_ai=use_ai, pack=pack, open_ui=open_ui)
    slim = {
        "exp_id": payload.get("exp_id"),
        "orders_sent": payload.get("orders_sent", 0),
        "brief_source": (payload.get("brief") or {}).get("source"),
        "artifact_html": payload.get("latest_html") or payload.get("artifact_html"),
        "disclaimer": payload.get("disclaimer"),
    }
    typer.echo(_json.dumps(_noneify(slim), ensure_ascii=False, separators=(",", ":")))


@app.command("paper-reconcile")
def paper_reconcile(
    window_days: int = typer.Option(
        30,
        "--window-days",
        help="Slippage ledger summary lookback when data/slippage_ledger.jsonl exists.",
    ),
) -> None:
    """Compare DecisionEngine targets vs paper_positions.json; no broker orders."""
    import json as _json
    from pathlib import Path as _Path

    from .shadow import desired_from_decisions, log_shadow_snapshot

    s = AppSettings()
    s.resolve_paths()
    data = load_universe_v2(s)
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    desired = desired_from_decisions(decisions)

    held: dict[str, float] = {}
    held_path = _Path(s.data.data_dir) / "paper_positions.json"
    if held_path.exists():
        raw = _json.loads(held_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            held = {str(k): float(v) for k, v in raw.items()}

    out: dict[str, Any] = log_shadow_snapshot(desired, held, tag="paper-reconcile")
    out["orders_sent"] = 0
    out["shadow_held_source"] = str(held_path) if held_path.exists() else None

    ledger_path = _Path(s.data.data_dir) / "slippage_ledger.jsonl"
    if ledger_path.exists():
        try:
            from . import slippage_ledger as _slippage_ledger

            out["slippage"] = _slippage_ledger.summarize(ledger_path, window_days)
        except ImportError:
            pass

    typer.echo(_json.dumps(_noneify(out), ensure_ascii=False, separators=(",", ":")))


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
    # Buy & Hold for comparison (benchmark may have been dropped by validation)
    bench = s.universe.benchmark if s.universe.benchmark in data else next(iter(data))
    px = data[bench]["close"].astype(float)
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


@app.command("research-panel")
def research_panel(exp_id: Optional[str] = None) -> None:
    """
    Generate the WARDEN research command panel (self-contained HTML).

    Multi-engine triage surface — NOT a profit promise / buy list.
    """
    import json as _json
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    from pathlib import Path as _Path

    from ..research.market_analyzer import analyze_market
    from ..research.multi_asset import DEFAULT_RESEARCH_SYMBOLS
    from ..research.panel import write_warden_panel

    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if list(s.universe.symbols) == ["SPY"]:
        s.universe.symbols = list(DEFAULT_RESEARCH_SYMBOLS)
    data = load_universe_v2(s)
    report = analyze_market(
        data,
        symbols=list(s.universe.symbols),
        benchmark=s.universe.benchmark if s.universe.benchmark in data else s.universe.symbols[0],
    )
    research_dir = _Path(s.data.reports_dir) / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    run_id = exp_id or _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    html_path = research_dir / f"warden_panel_{run_id}.html"
    write_warden_panel(report, str(html_path), generated_at=run_id)
    payload = {
        "exp_id": run_id,
        "phase": "V3-warden-panel",
        "model": report.get("model"),
        "posture": report.get("posture"),
        "action_counts": report.get("action_counts"),
        "panel": str(html_path),
        "artifact": str(html_path),
        "disclaimer": report.get("disclaimer"),
    }
    meta = research_dir / f"warden_panel_{run_id}.json"
    meta.write_text(
        _json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":"), indent=2),
        encoding="utf-8",
    )
    payload["meta"] = str(meta)
    typer.echo(_json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":")))


@app.command("market-analyze")
def market_analyze() -> None:
    """
    Multi-factor market scorecard (trend / RS / risk / breadth).

    Research triage only — ranks AVOID / WATCH / RESEARCH_CANDIDATE.
    Does NOT promise profits or 'almost never lose'.
    """
    import json as _json
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    from pathlib import Path as _Path

    from ..intelligence.market_radar import build_market_radar
    from ..research.market_analyzer import analyze_market
    from ..research.multi_asset import DEFAULT_RESEARCH_SYMBOLS

    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if list(s.universe.symbols) == ["SPY"]:
        s.universe.symbols = list(DEFAULT_RESEARCH_SYMBOLS)
    data = load_universe_v2(s)
    report = analyze_market(
        data,
        symbols=list(s.universe.symbols),
        benchmark=s.universe.benchmark if s.universe.benchmark in data else s.universe.symbols[0],
    )
    radar = build_market_radar(data)
    research_dir = _Path(s.data.reports_dir) / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    run_id = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    art = research_dir / f"market_analyze_{run_id}.json"
    payload = {
        "exp_id": run_id,
        "phase": "V3-market-analyzer",
        "report": report,
        "market_radar": radar,
        "artifact": str(art),
        "note": report.get("disclaimer"),
    }
    art.write_text(
        _json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":"), indent=2),
        encoding="utf-8",
    )
    typer.echo(_json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":")))


@app.command("research-run")
def research_run(
    exp_id: Optional[str] = None,
    profile: str = typer.Option(
        "full",
        "--profile",
        help="Research suite profile: smoke (fast SMA+DSR) or full.",
    ),
    confirmation: bool = typer.Option(
        False,
        "--confirmation",
        help=(
            "Open the frozen hold-out (RESEARCH__HOLDOUT_START) for a ONE-TIME confirmation run. "
            "Every opening is logged in <reports>/research/holdout_openings.jsonl; beyond "
            "RESEARCH__MAX_HOLDOUT_OPENINGS every row FAILs with holdout_overused. "
            "The flag must be typed explicitly: RESEARCH__CONFIRMATION_MODE alone is ignored."
        ),
    ),
) -> None:
    """
    V3 research suite: gated strategy tracks + loss-mitigation overlays +
    multi-factor market analyzer + overfitting/cost diagnostics.
    Does not change production strategy defaults. Most candidates are expected to FAIL gates.
    """
    import json as _json
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    from pathlib import Path as _Path

    from ..research.multi_asset import DEFAULT_RESEARCH_SYMBOLS

    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    # The hold-out opens only with the explicit flag — never from env/.env alone.
    if s.research.confirmation_mode and not confirmation:
        log.warning(
            "research_confirmation_mode_ignored: RESEARCH__CONFIRMATION_MODE is set but --confirmation "
            "was not typed; running with the frozen hold-out hidden"
        )
        s.research.confirmation_mode = False
    if confirmation:
        if not s.research.holdout_start:
            raise typer.BadParameter(
                "no frozen hold-out is declared: set RESEARCH__HOLDOUT_START=YYYY-MM-DD before confirming",
                param_hint="--confirmation",
            )
        s.research.confirmation_mode = True
    # Expand single-name default to the research ETF cross-section (full only).
    if profile != "smoke" and list(s.universe.symbols) == ["SPY"]:
        s.universe.symbols = list(DEFAULT_RESEARCH_SYMBOLS)
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    run_id = exp_id or _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    if confirmation:
        _log_path = holdout_openings_path(s.data.reports_dir)
        _opening_no = count_holdout_openings(_log_path, s.research.holdout_start) + 1
        _max_open = int(s.research.max_holdout_openings)
        typer.secho(
            f"HOLD-OUT OPENING: run {run_id} is using bars on/after {s.research.holdout_start} "
            f"(opening no. {_opening_no} of {_max_open} allowed). Logged in {_log_path}. "
            "If this idea fails here, it is dead: do not retune it on these bars.",
            fg=typer.colors.RED,
            bold=True,
            err=True,
        )
        if _opening_no > _max_open:
            typer.secho(
                f"HOLD-OUT OVERUSED: opening no. {_opening_no} exceeds the {_max_open} allowed. "
                "Every candidate row of this run will FAIL with reason holdout_overused.",
                fg=typer.colors.RED,
                bold=True,
                err=True,
            )
    suite = run_research_suite(
        s,
        data,
        sym,
        direction=s.trading.direction,
        profile=profile,
        exp_id=run_id,
        reports_dir=s.data.reports_dir,
    )
    results = list(suite.get("candidates") or [])
    research_dir = _Path(s.data.reports_dir) / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    registry_path = research_dir / f"experiments_{run_id}.jsonl"
    records = build_experiment_records(
        results,
        exp_id=run_id,
        git_commit=git_commit(),
        dataset_hash=dataset_hash(data),
        config_hash=config_hash(s),
        suite_summary=suite,
    )
    for rec in records:
        save_experiment(registry_path, rec)
    n_pass = int(suite.get("n_pass") or 0)
    n_fail = int(suite.get("n_fail") or 0)
    n_pass_loose = int(suite.get("n_pass_loose") or 0)
    if profile == "smoke":
        suite_label = "sma+dsr (smoke)"
    else:
        suite_label = (
            "sma+regime+cost_ladder+tsmom+mean_reversion+loss_mitigation+xsection+"
            "embargo+pbo+multi_asset+cpcv+dsr+turnover+market_analyzer"
        )
    payload = {
        "exp_id": run_id,
        "symbol": sym,
        "symbols": list(s.universe.symbols),
        "phase": "V3-research",
        "suite": suite_label,
        "n_candidates": int(suite.get("n_candidates") or len(results)),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_pass_loose": n_pass_loose,
        "gate_mode": "strict",
        # Research discipline (playbook phase 1): trial budget + frozen hold-out.
        "n_trials": int(suite.get("n_trials") or 0),
        "years_available": suite.get("years_available"),
        "years_needed": suite.get("years_needed"),
        "budget_ok": suite.get("budget_ok"),
        "holdout_start": suite.get("holdout_start"),
        "holdout_applied": bool(suite.get("holdout_applied")),
        "holdout_opened": bool(suite.get("holdout_opened")),
        "holdout_overused": bool(suite.get("holdout_overused")),
        "budget": suite.get("budget"),
        "holdout": suite.get("holdout"),
        "cost_fragility": suite.get("cost_fragility"),
        "loss_mitigation_summary": suite.get("loss_mitigation_summary"),
        "embargo_sensitivity": suite.get("embargo_sensitivity"),
        "pbo": suite.get("pbo"),
        "cross_section": suite.get("cross_section"),
        "cpcv": suite.get("cpcv"),
        "dsr": suite.get("dsr"),
        "turnover": suite.get("turnover"),
        "market_analyzer": suite.get("market_analyzer"),
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
                "loss_mitigation",
                "xsection",
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
                "gate_passed_loose": bool(r.get("gate_passed_loose")),
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
            "Passing gates ≠ deploy. Loss mitigation + analyzer are triage tools, "
            "not profit guarantees. See docs/research/INSTITUTIONAL_SYSTEMATIC_STACK.md"
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


@app.command("research-portfolio")
def research_portfolio(
    exp_id: Optional[str] = None,
    profile: str = typer.Option(
        "smoke",
        "--profile",
        help="Phase-2 profile: smoke (1 config) or full (rules × weighting grid).",
    ),
    universe: Optional[str] = typer.Option(
        None,
        "--universe",
        help="Path to UniverseSpec JSON (default: DATA__UNIVERSE_FILE or config/universe-10etf.json).",
    ),
    confirmation: bool = typer.Option(
        False,
        "--confirmation",
        help="Open the frozen hold-out once (same semantics as research-run --confirmation).",
    ),
) -> None:
    """
    Phase-2 portfolio research: pipeline stage graph vs 60/40 + All Weather + random portfolios.
    Strict gates decide PASS/FAIL. PASS ≠ deploy.
    """
    import json as _json
    from dataclasses import fields as _dc_fields
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    from pathlib import Path as _Path

    from ..data.universe import load_universe_spec
    from ..research.portfolio_runner import RECOMMENDATION_FAIL, run_portfolio_research
    from ..research.registry import ExperimentRecord, save_experiment

    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if profile not in {"smoke", "full"}:
        raise typer.BadParameter("profile must be smoke|full", param_hint="--profile")
    if s.research.confirmation_mode and not confirmation:
        log.warning(
            "research_confirmation_mode_ignored: RESEARCH__CONFIRMATION_MODE is set but "
            "--confirmation was not typed; running with the frozen hold-out hidden"
        )
        s.research.confirmation_mode = False
    if confirmation:
        if not s.research.holdout_start:
            raise typer.BadParameter(
                "no frozen hold-out is declared: set RESEARCH__HOLDOUT_START=YYYY-MM-DD before confirming",
                param_hint="--confirmation",
            )
        s.research.confirmation_mode = True

    uni_path = universe or s.data.universe_file or "config/universe-10etf.json"
    uni = load_universe_spec(uni_path)
    s.universe.symbols = list(uni.symbols)
    if s.universe.benchmark not in set(uni.symbols):
        s.universe.benchmark = uni.symbols[0]
    data = load_universe_v2(s)
    allowed = set(uni.symbols)
    data = {sym: df for sym, df in data.items() if sym in allowed}
    if not data:
        raise typer.BadParameter(f"no prices loaded for universe symbols {list(uni.symbols)}")
    run_id = exp_id or _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = run_portfolio_research(
        data, s, uni, profile=profile, exp_id=run_id, reports_dir=s.data.reports_dir  # type: ignore[arg-type]
    )
    research_dir = _Path(s.data.reports_dir) / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    registry_path = research_dir / f"portfolio_experiments_{run_id}.jsonl"
    known = {f.name for f in _dc_fields(ExperimentRecord)}
    for rec in summary.get("registry_records") or []:
        if isinstance(rec, ExperimentRecord):
            save_experiment(registry_path, rec)
        elif isinstance(rec, dict):
            save_experiment(registry_path, ExperimentRecord(**{k: v for k, v in rec.items() if k in known}))
    payload = {k: v for k, v in summary.items() if k not in {"registry_records"}}
    payload["registry"] = str(registry_path)
    if not payload.get("artifact"):
        art = research_dir / f"portfolio_{run_id}.json"
        art.write_text(
            _json.dumps(_noneify(summary), ensure_ascii=False, separators=(",", ":"), indent=2),
            encoding="utf-8",
        )
        payload["artifact"] = str(art)
    if summary.get("verdict") == "FAIL":
        typer.echo(RECOMMENDATION_FAIL, err=True)
    # JSON on stdout (same as research-run) so tests/automation can parse the payload.
    typer.echo(_json.dumps(_noneify(payload), ensure_ascii=False, separators=(",", ":")))


# --------------------------------------------------------------------------- golden files (Lean-style)
#
# One frozen snapshot per strategy over the deterministic fixtures: stats + hash of
# the order list. ``tests/test_golden.py`` recomputes them on every run and fails on
# any drift; they are regenerated ONLY on purpose with ``ibtrader golden-regen --yes``
# and committed explicitly (annex 5 §4: QuantConnect Lean ``ExpectedStatistics``).

GOLDEN_STRATEGIES: tuple[str, ...] = ("sma_crossover", "tsmom", "rotation", "mean_reversion")
GOLDEN_REGEN_COMMAND = "ibtrader golden-regen --yes"
GOLDEN_FLOAT_REL_TOL = 1e-9
# Compared bit-for-bit; every other numeric field uses GOLDEN_FLOAT_REL_TOL.
GOLDEN_EXACT_KEYS: tuple[str, ...] = ("config_hash", "dataset_hash", "orders_hash", "n_orders", "n_bars", "universe")
GOLDEN_EXACT_STATS: tuple[str, ...] = ("trade_count",)
GOLDEN_BASE_SYMBOL = "SPY"
_GOLDEN_SYNTHETIC_DOC = {
    "SYN_REV": "SPY fixture OHLC reversed in time (a clean down-trend); volume kept",
    "SYN_WAVE": "sawtooth close = 100 + 0.5*(i mod 40): +0.5/bar for 39 bars then a one-bar reset of -19.5 "
    "(exact IEEE arithmetic, ~16% gap that crosses a 2-sigma Bollinger band); "
    "open=close, high=close+1, low=close-1, volume=1e6",
}


def golden_settings(universe: list[str]) -> AppSettings:
    """Deterministic settings for golden runs: library defaults, no ``.env``, no env vars.

    ``AppSettings.model_construct`` bypasses pydantic-settings' sources, so a
    developer's shell or ``.env`` cannot move a golden; only a code change can.
    """
    s = AppSettings.model_construct()
    s.data.providers = ["fixture"]
    s.engine.use_cache = False
    s.universe.symbols = list(universe)
    s.universe.benchmark = GOLDEN_BASE_SYMBOL
    return s


def _golden_synthetic(base: _pd.DataFrame) -> dict[str, _pd.DataFrame]:
    """Deterministic companions derived from the fixture (pure arithmetic, bit-identical everywhere)."""
    idx = base.index
    n = len(idx)
    i = np.arange(n, dtype=float)
    cols = ["open", "high", "low", "close", "volume"]
    rev = base[cols].astype(float).iloc[::-1].reset_index(drop=True)
    rev.index = idx
    rev = rev.copy()
    # Reversed OHLC keeps high >= low; nothing else to fix.
    # Sawtooth: a smooth wave never leaves a 2-sigma Bollinger band, a periodic gap does.
    close = 100.0 + 0.5 * np.mod(i, 40.0)  # 100 .. 119.5, resets every 40 bars
    wave = _pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    return {"SYN_REV": rev, "SYN_WAVE": wave}


def golden_universe(strategy: str, fixture_dir: str | None = None) -> dict[str, _pd.DataFrame]:
    """Frames a golden strategy runs on. SPY comes from ``tests/fixtures``; the rest is derived."""
    if strategy not in GOLDEN_STRATEGIES:
        raise ValueError(f"unknown golden strategy {strategy!r}; expected one of {GOLDEN_STRATEGIES}")
    base = FixtureProvider(fixture_dir).fetch_daily_ohlcv(GOLDEN_BASE_SYMBOL).data
    base = base[["open", "high", "low", "close", "volume"]].astype(float)
    if strategy in ("sma_crossover", "tsmom"):
        return {GOLDEN_BASE_SYMBOL: base}
    syn = _golden_synthetic(base)
    if strategy == "mean_reversion":
        return {GOLDEN_BASE_SYMBOL: base, "SYN_WAVE": syn["SYN_WAVE"]}
    return {GOLDEN_BASE_SYMBOL: base, "SYN_REV": syn["SYN_REV"], "SYN_WAVE": syn["SYN_WAVE"]}


def golden_strategy(strategy: str, settings: AppSettings) -> tuple[Strategy, dict[str, Any]]:
    """Strategy instance + the params recorded in the golden (repo defaults, not tuned)."""
    direction = settings.trading.direction
    if strategy == "sma_crossover":
        fast = int(settings.strategy.params.get("fast_window", 10))
        slow = int(settings.strategy.params.get("slow_window", 30))
        base = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
        return _DirectionWrapper(base, direction), {"fast_window": fast, "slow_window": slow}
    if strategy == "tsmom":
        from ..research.tsmom_runner import DEFAULT_TSMOM_LOOKBACKS

        lookback = int(DEFAULT_TSMOM_LOOKBACKS[0])
        return TimeSeriesMomentum(lookback=lookback, allow_short=direction != "long_only"), {"lookback": lookback}
    if strategy == "rotation":
        from ..research.xsection_runner import DEFAULT_XSECTION_CANDIDATES

        lookback, top_n = DEFAULT_XSECTION_CANDIDATES[0]
        return CrossSectionalMomentum(lookback_days=int(lookback), top_n=int(top_n)), {
            "lookback_days": int(lookback),
            "top_n": int(top_n),
        }
    if strategy == "mean_reversion":
        from ..research.mean_reversion_runner import DEFAULT_MR_CANDIDATES

        window, num_std = DEFAULT_MR_CANDIDATES[0]
        return MeanReversion(window=int(window), num_std=float(num_std)), {
            "window": int(window),
            "num_std": float(num_std),
        }
    raise ValueError(f"unknown golden strategy {strategy!r}; expected one of {GOLDEN_STRATEGIES}")


def orders_hash(trades: list[tuple[str, str, int, float, str]]) -> str:
    """SHA-256 of the serialized order list: (date, symbol, qty, price rounded to 6 dp), in order."""
    import hashlib as _hashlib
    import json as _json

    rows = [[str(d), str(sym), int(q), round(float(p), 6)] for d, sym, q, p, *_ in trades]
    blob = _json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    return _hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compute_golden_snapshot(strategy: str, fixture_dir: str | None = None) -> dict[str, Any]:
    """Run ``strategy`` on the golden universe with default settings and freeze what matters.

    Shared by ``ibtrader golden-regen`` (writer) and ``tests/test_golden.py`` (checker).
    """
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    data = golden_universe(strategy, fixture_dir)
    universe = list(data.keys())
    s = golden_settings(universe)
    strat, params = golden_strategy(strategy, s)
    result = backtest(
        data=data,
        strategy=strat,
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
        rebalance_band_pct=float(s.trading.rebalance_band_pct),
        benefit_bps=float(s.trading.benefit_bps),
        risk_cost_bps=float(s.trading.risk_cost_bps),
        direction=s.trading.direction,
        risk_on=None,
        risk_on_threshold=float(s.risk.risk_on_threshold),
        target_vol_annual=float(s.risk.target_vol_annual),
    )
    st = result.stats
    trades = list(result.trades)
    stats: dict[str, Any] = {
        "sharpe": float(st.sharpe),
        "cagr": float(st.cagr),
        "max_dd": float(st.max_drawdown),
        "trade_count": int(st.trade_count),
        "total_commission": float(st.total_commission),
        "turnover": float(st.turnover),
        "final_equity": float(result.equity_curve.iloc[-1]) if len(result.equity_curve) else float("nan"),
    }
    return {
        "strategy": strategy,
        "generated_at_utc": _dt.now(_tz.utc).isoformat(),
        "git_commit": git_commit(),
        "config_hash": config_hash(s),
        "dataset_hash": dataset_hash(data),
        "universe": universe,
        "fixtures": [f"{GOLDEN_BASE_SYMBOL}_1d.csv"],
        "synthetic": {k: _GOLDEN_SYNTHETIC_DOC[k] for k in universe if k in _GOLDEN_SYNTHETIC_DOC},
        "params": params,
        "direction": s.trading.direction,
        "n_bars": int(len(data[GOLDEN_BASE_SYMBOL])),
        "stats": _noneify(stats),
        "orders_hash": orders_hash(trades),
        "n_orders": len(trades),
        "regenerate": GOLDEN_REGEN_COMMAND,
    }


def compare_golden(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Human-readable list of drifts between a stored golden and a fresh snapshot (empty = match).

    Hashes, integers and the universe must match exactly; floats within
    ``GOLDEN_FLOAT_REL_TOL``; ``None`` (NaN on disk) only equals ``None``.
    ``generated_at_utc`` / ``git_commit`` are provenance, never compared.
    """
    import math as _math

    diffs: list[str] = []
    for key in GOLDEN_EXACT_KEYS:
        if expected.get(key) != actual.get(key):
            diffs.append(f"{key}: expected {expected.get(key)!r}, got {actual.get(key)!r}")
    exp_stats = dict(expected.get("stats") or {})
    act_stats = dict(actual.get("stats") or {})
    for name in sorted(set(exp_stats) | set(act_stats)):
        e, a = exp_stats.get(name), act_stats.get(name)
        if name in GOLDEN_EXACT_STATS:
            if e != a:
                diffs.append(f"stats.{name}: expected {e!r}, got {a!r}")
            continue
        if e is None or a is None:
            if e is not a:
                diffs.append(f"stats.{name}: expected {e!r}, got {a!r}")
            continue
        try:
            ef, af = float(e), float(a)
        except (TypeError, ValueError):
            if e != a:
                diffs.append(f"stats.{name}: expected {e!r}, got {a!r}")
            continue
        if not _math.isclose(ef, af, rel_tol=GOLDEN_FLOAT_REL_TOL, abs_tol=0.0):
            diffs.append(f"stats.{name}: expected {ef!r}, got {af!r} (rel tol {GOLDEN_FLOAT_REL_TOL})")
    if dict(expected.get("params") or {}) != dict(actual.get("params") or {}):
        diffs.append(f"params: expected {expected.get('params')!r}, got {actual.get('params')!r}")
    return diffs


def regenerate_golden_files(out_dir: str = "tests/golden", fixture_dir: str | None = None) -> dict[str, Any]:
    """Write ``<out_dir>/<strategy>.json`` for every golden strategy; returns a digest."""
    import json as _json
    from pathlib import Path as _Path

    out = _Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Any] = {}
    for strategy in GOLDEN_STRATEGIES:
        snap = compute_golden_snapshot(strategy, fixture_dir)
        path = out / f"{strategy}.json"
        path.write_text(
            _json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written[strategy] = {
            "path": str(path),
            "n_orders": snap["n_orders"],
            "orders_hash": snap["orders_hash"],
            "stats": snap["stats"],
        }
    return {"out_dir": str(out), "strategies": list(GOLDEN_STRATEGIES), "written": written}


@app.command("golden-regen")
def golden_regen(
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Required. Overwrites tests/golden/*.json; commit the result explicitly (never from CI).",
    ),
    out_dir: str = typer.Option("tests/golden", "--out-dir", help="Where the golden JSON files live."),
    fixture_dir: Optional[str] = typer.Option(
        None, "--fixture-dir", help="Fixture directory (default: DATA__FIXTURE_DIR or ./tests/fixtures)."
    ),
) -> None:
    """
    Regenerate the golden files (Lean-style ExpectedStatistics) for sma_crossover, tsmom,
    rotation and mean_reversion over tests/fixtures. CI compares every run against them
    (tests/test_golden.py), so run this ONLY after an intended engine/cost/strategy change
    and commit the new JSON in its own explicit commit.
    """
    import json as _json

    if not yes:
        typer.secho(
            "golden-regen rewrites the frozen expected statistics under tests/golden/. "
            "Only do it after an intended change to the engine, costs or a strategy, and commit the "
            f"JSON explicitly. Re-run with: {GOLDEN_REGEN_COMMAND}",
            fg=typer.colors.RED,
            bold=True,
            err=True,
        )
        raise typer.Exit(code=2)
    digest = regenerate_golden_files(out_dir=out_dir, fixture_dir=fixture_dir)
    typer.echo(_json.dumps(_noneify(digest), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    app()
