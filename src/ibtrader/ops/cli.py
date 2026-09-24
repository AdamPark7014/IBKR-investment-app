from __future__ import annotations

from typing import Optional

import typer
from rich import print as rprint

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

app = typer.Typer(no_args_is_help=True)
log = setup_logging()

KNOWN_TRADING_VARS = {"TRADING__ALLOW_SHORT", "TRADING__REBALANCE_BAND_PCT", "TRADING__DIRECTION"}

def warn_unknown_trading_env() -> None:
    import os as _os

    unknown = [
        k for k in _os.environ.keys() if k.startswith("TRADING__") and k not in KNOWN_TRADING_VARS
    ]
    if unknown:
        log.warning("unknown_trading_env_vars %s", unknown)


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
def backtest_sample(symbol: Optional[str] = None, exp_id: Optional[str] = None) -> None:
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    strat = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=bool(s.trading.allow_short),
    )
    result = backtest(
        data=data,
        strategy=strat,
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
        rebalance_band_pct=float(s.trading.rebalance_band_pct),
        benefit_bps=float(s.trading.benefit_bps),
        risk_cost_bps=float(s.trading.risk_cost_bps),
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
    rprint(
        {
            "report": out,
            "settings": {
                "allow_short": s.trading.allow_short,
                "rebalance_band_pct": s.trading.rebalance_band_pct,
                "direction": s.trading.direction,
            },
            "cagr": result.stats.cagr,
            "sharpe": result.stats.sharpe,
            "sortino": result.stats.sortino,
            "max_dd": result.stats.max_drawdown,
            "win_rate": result.stats.win_rate,
            "exposure": result.stats.exposure,
            "calmar": result.stats.calmar,
            "recovery_factor": result.stats.recovery_factor,
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
        res = backtest(
            data=data,
            strategy=strat,
            commission_cfg=s.commission,
            slippage_cfg=s.slippage,
            rebalance_band_pct=float(s.trading.rebalance_band_pct),
            benefit_bps=float(s.trading.benefit_bps),
            risk_cost_bps=float(s.trading.risk_cost_bps),
        )
        results[m] = {
            "cagr": res.stats.cagr,
            "sharpe": res.stats.sharpe,
            "sortino": res.stats.sortino,
            "calmar": res.stats.calmar,
            "max_dd": res.stats.max_drawdown,
            "trade_count": res.stats.trade_count,
            "commission": res.stats.total_commission,
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


if __name__ == "__main__":
    app()


@app.command("paper-run")
def paper_run() -> None:
    s = AppSettings()
    s.resolve_paths()
    data = load_universe_data(s.universe, s.engine, s.data)
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

