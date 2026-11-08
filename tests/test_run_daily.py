"""Daily run: plan (shadow / orders) and execute with a fake broker (audit 2026-11-07, §5)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.execution.order_manager import BrokerOrderStatus, OrderGateway
from ibtrader.ops.config_freeze import write_freeze
from ibtrader.ops.notify import check_heartbeat
from ibtrader.ops.run_daily import run_execute, run_plan

ET = ZoneInfo("America/New_York")
PLAN_AT = datetime(2026, 11, 9, 16, 45, tzinfo=ET)  # Monday after the close
EXEC_AT = datetime(2026, 11, 10, 9, 40, tzinfo=ET)  # Tuesday after the open


def _frames(last="2026-11-09") -> Dict[str, pd.DataFrame]:
    idx = pd.bdate_range(end=last, periods=300)
    rng = np.random.default_rng(1)
    out = {}
    for sym, px in (("SPY", 500.0), ("IEF", 95.0)):
        c = px * np.exp(np.cumsum(rng.normal(0, 0.005, len(idx))))
        out[sym] = pd.DataFrame({"close": c, "close_raw": c}, index=idx)
    return out


def _settings(tmp: Path, **exec_kw) -> AppSettings:
    s = AppSettings(_env_file=None)
    s.data.data_dir = str(tmp / "data")
    s.data.reports_dir = str(tmp / "reports")
    s.risk.killswitch_file = str(tmp / "data" / "KILL_SWITCH")
    s.ops.alerts_file = str(tmp / "data" / "alerts.jsonl")
    s.ops.heartbeat_file = str(tmp / "data" / "heartbeat.json")
    s.universe.symbols = ["SPY", "IEF"]
    s.strategy.name = "static"
    s.strategy.params = {"weights": {"SPY": 0.3, "IEF": 0.3}}
    s.pretrade.capital_usd = 50_000.0
    s.pretrade.max_order_notional_usd = 20_000.0
    for k, v in exec_kw.items():
        setattr(s.execution, k, v)
    return s


def test_plan_shadow_trades_paper_book_and_heartbeat(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    rep = run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    assert rep["status"] == "ok", rep
    assert rep["book_initialized"] is True
    assert {o["symbol"] for o in rep["pretrade"]["approved"]} == {"SPY", "IEF"}
    book = json.loads((tmp_path / "data" / "paper_account.json").read_text())
    assert book["basis"] == "shadow" and book["shares"]["SPY"] > 0 and book["cash"] < 50_000
    assert rep["nav_after"] < rep["nav_before"]  # spread + commission are paid
    assert (tmp_path / "data" / "paper_equity.jsonl").read_text().count("\n") == 1
    assert check_heartbeat(s.ops, now=PLAN_AT.astimezone()).get("ok") is True
    # Second day: already at target → no new orders (min notional), book unchanged.
    rep2 = run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    assert rep2["pretrade"]["n_approved"] == 0


def test_plan_stale_data_blocks_new_risk(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    rep = run_plan(s, loader=lambda _s: _frames(last="2026-11-06"), now=PLAN_AT)
    assert "data" in rep["blocks"] and rep["status"] == "blocked_new_risk"
    assert rep["pretrade"]["n_approved"] == 0
    alerts = (tmp_path / "data" / "alerts.jsonl").read_text()
    assert "data_quality" in alerts


def test_plan_loader_error_is_critical_and_no_heartbeat(tmp_path: Path) -> None:
    s = _settings(tmp_path)

    def boom(_s):
        raise RuntimeError("Tiingo 401")

    rep = run_plan(s, loader=boom, now=PLAN_AT)
    assert rep["status"] == "data_error"
    assert not (tmp_path / "data" / "heartbeat.json").exists()


def test_plan_orders_mode_without_freeze_blocks(tmp_path: Path) -> None:
    s = _settings(tmp_path, mode="paper_orders")
    s.trading.allow_broker_orders = True
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "paper_account.json").write_text(json.dumps({"cash": 50_000, "shares": {}}))
    rep = run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    assert any(b.startswith("freeze:") for b in rep["blocks"])
    assert rep["pretrade"]["n_approved"] == 0


class Broker(OrderGateway):
    def __init__(self, shares: Dict[str, int], cash: float, *, fill: bool = True, acct: str = "DU1") -> None:
        self.shares = dict(shares)
        self.cash = cash
        self.fill = fill
        self.acct = acct
        self.orders: Dict[str, Tuple[str, str, int, float]] = {}

    def existing_refs(self, prefix: str) -> Dict[str, str]:
        return {}

    def midpoint(self, symbol: str) -> Optional[float]:
        return {"SPY": 510.0, "IEF": 96.0}[symbol]

    def place_limit(self, symbol, side, qty, limit, order_ref) -> str:
        bid = str(len(self.orders) + 1)
        self.orders[bid] = (symbol, side, qty, limit)
        if self.fill:
            sign = 1 if side == "BUY" else -1
            self.shares[symbol] = self.shares.get(symbol, 0) + sign * qty
            self.cash -= sign * qty * limit + 1.0
        return bid

    def place_adaptive_market(self, symbol, side, qty, order_ref) -> str:
        return self.place_limit(symbol, side, qty, self.midpoint(symbol) or 0.0, order_ref)

    def status(self, broker_id: str) -> BrokerOrderStatus:
        sym, side, qty, px = self.orders[broker_id]
        if self.fill:
            return BrokerOrderStatus("Filled", qty, 0, px)
        return BrokerOrderStatus("Submitted", 0, qty, 0.0)

    def cancel(self, broker_id: str) -> None:
        pass

    def account_snapshot(self):
        return {k: v for k, v in self.shares.items() if v}, self.cash, self.acct

    def sleep(self, seconds: float) -> None:
        pass


def _orders_ready(tmp_path: Path) -> AppSettings:
    s = _settings(tmp_path, mode="paper_orders", order_timeout_sec=1)
    s.trading.allow_broker_orders = True
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "paper_account.json").write_text(json.dumps({"cash": 50_000.0, "shares": {}}))
    write_freeze(tmp_path / "data" / "paper_config_freeze.json", s)
    return s


def test_plan_then_execute_paper_orders(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    rep = run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    assert rep["status"] == "ok", rep["blocks"]
    assert Path(rep["pending_orders"]).exists()
    broker = Broker({}, 50_000.0)
    ex = run_execute(s, gateway_factory=lambda _s: broker, now=EXEC_AT)
    assert ex["status"] == "ok", ex
    assert ex["orders_sent"] == 2
    assert ex["reconcile_after"]["ok"] is True
    book = json.loads((tmp_path / "data" / "paper_account.json").read_text())
    assert book["basis"] == "broker" and book["shares"] == broker.shares
    assert (tmp_path / "data" / "pending_orders.done.json").exists()
    slip = (tmp_path / "data" / "slippage_ledger.jsonl").read_text().splitlines()
    assert len(slip) == 2


def test_execute_refuses_stale_pending_and_breaks(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    late = datetime(2026, 11, 11, 9, 40, tzinfo=ET)  # two sessions later
    ex = run_execute(s, gateway_factory=lambda _s: Broker({}, 50_000.0), now=late)
    assert ex["status"] == "pending_stale"
    # A book that does not match the broker → kill switch, nothing sent.
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    broker = Broker({"SPY": 7}, 50_000.0)
    ex2 = run_execute(s, gateway_factory=lambda _s: broker, now=EXEC_AT)
    assert ex2["status"] == "reconcile_break_before" and broker.orders == {}
    assert Path(s.risk.killswitch_file).exists()


def test_execute_not_permitted_without_allow_flag(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    s.trading.allow_broker_orders = False
    ex = run_execute(s, gateway_factory=lambda _s: Broker({}, 50_000.0), now=EXEC_AT)
    assert ex["status"] == "not_permitted"


def test_exit_codes_and_secondary_loader() -> None:
    from ibtrader.ops.run_daily import exit_code_for, primary_provider, secondary_loader_for

    assert exit_code_for("ok") == 0 and exit_code_for("blocked_new_risk") == 1
    assert exit_code_for("reconcile_break_before") == 2 and exit_code_for("data_error") == 2
    s = AppSettings(_env_file=None)
    s.data.providers = ["tiingo", "yahoo"]
    s.data.tiingo_token = ""
    assert primary_provider(s) == "yahoo" and secondary_loader_for(s) is None
    s.data.tiingo_token = "x"
    assert primary_provider(s) == "tiingo" and secondary_loader_for(s) is not None


def test_cli_heartbeat_check_exit_code(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from ibtrader.ops.cli import app

    monkeypatch.setenv("OPS__HEARTBEAT_FILE", str(tmp_path / "hb.json"))
    monkeypatch.setenv("OPS__ALERTS_FILE", str(tmp_path / "alerts.jsonl"))
    r = CliRunner().invoke(app, ["heartbeat-check"])
    assert r.exit_code == 2 and "heartbeat_missing" in r.output


def test_scorecard_after_shadow_runs(tmp_path: Path) -> None:
    from ibtrader.ops.scorecard import build_scorecard

    s = _settings(tmp_path)
    empty = build_scorecard(s)
    assert empty["ready_for_live"] is False and empty["n_pass"] == 0
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    sc = build_scorecard(s)
    by = {m["metric"]: m for m in sc["metrics"]}
    assert by["heartbeats_perdidos"]["status"] == "pass"
    assert by["descuadres_con_broker"]["status"] == "pass"
    assert by["sesiones_en_paper"]["status"] == "fail" and by["slippage_mediano"]["status"] == "insufficient"
    assert sc["ready_for_live"] is False
