from __future__ import annotations

from typing import Optional

import typer
from rich import print as rprint

from ..backtest.engine import backtest
from ..backtest.report import save_equity_report
from ..config import AppSettings
from ..data.downloader import load_universe_data
from ..engine.decision import DecisionEngine
from ..logging import setup_logging
from ..ops.killswitch import activate_killswitch, clear_killswitch
from ..ops.status import status_summary
from ..strategy.sma_crossover import SMACrossover

app = typer.Typer(no_args_is_help=True)
log = setup_logging()


@app.command()
def status() -> None:
    s = AppSettings()
    s.resolve_paths()
    rprint(status_summary(s))


@app.command("download-data")
def download_data() -> None:
    s = AppSettings()
    s.resolve_paths()
    data = load_universe_data(s.universe, s.engine, s.data)
    rprint({k: len(v) for k, v in data.items()})


@app.command()
def backtest_sample(symbol: Optional[str] = None) -> None:
    s = AppSettings()
    s.resolve_paths()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_data(s.universe, s.engine, s.data)
    strat = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
    )
    result = backtest(
        data=data,
        strategy=strat,
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
    )
    out = save_equity_report(result, s.data.reports_dir, name="sample_backtest")
    rprint(
        {
            "report": out,
            "cagr": result.stats.cagr,
            "sharpe": result.stats.sharpe,
            "sortino": result.stats.sortino,
            "max_dd": result.stats.max_drawdown,
            "win_rate": result.stats.win_rate,
            "exposure": result.stats.exposure,
        }
    )


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

