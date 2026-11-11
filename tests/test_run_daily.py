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
EXEC_AT = datetime(2026, 11, 10, 10, 5, tzinfo=ET)  # Tuesday, 35 min after the open


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


def test_execute_overwrites_yesterdays_done_file(tmp_path: Path) -> None:
    # Path.rename fails on Windows when the target exists: on 11-11 the execute filled every order
    # and then died with exit 2 because pending_orders.done.json was still there from the day before.
    s = _orders_ready(tmp_path)
    (tmp_path / "data" / "pending_orders.done.json").write_text("{}")
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    ex = run_execute(s, gateway_factory=lambda _s: Broker({}, 50_000.0), now=EXEC_AT)
    assert ex["status"] == "ok", ex
    assert json.loads((tmp_path / "data" / "pending_orders.done.json").read_text()) != {}
    assert not (tmp_path / "data" / "pending_orders.json").exists()


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


def test_execute_waits_until_spreads_settle_after_open(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    broker = Broker({}, 50_000.0)
    early = datetime(2026, 11, 10, 9, 40, tzinfo=ET)  # 10 min after the open: wide spreads
    ex = run_execute(s, gateway_factory=lambda _s: broker, now=early)
    assert ex["status"] == "too_early" and broker.orders == {}
    assert (tmp_path / "data" / "pending_orders.json").exists()
    from ibtrader.ops.run_daily import exit_code_for
    assert exit_code_for("too_early") == 0


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


def test_shadow_book_receives_dividends_and_splits() -> None:
    from datetime import date as _date

    from ibtrader.ops.run_daily import credit_corporate_actions

    idx = pd.bdate_range("2026-11-02", periods=4)
    raw = pd.Series([100.0, 100.0, 99.0, 49.5], index=idx)  # $1 dividend on day 3, 2:1 split on day 4
    adj = pd.Series([99.0, 99.0, 99.0, 99.0], index=idx)
    data = {"VNQ": pd.DataFrame({"close": adj, "close_raw": raw})}
    book = {"cash": 0.0, "shares": {"VNQ": 10}}
    ev = credit_corporate_actions(book, data, _date(2026, 11, 2), _date(2026, 11, 5))
    assert abs(book["cash"] - 10.0) < 1e-6 and book["shares"]["VNQ"] == 20
    assert [("dividend_per_share" in e, "split" in e) for e in ev] == [(True, False), (False, True)]
    assert credit_corporate_actions({"cash": 0, "shares": {"VNQ": 1}}, data, None, _date(2026, 11, 5)) == []


def test_live_trades_only_when_target_moves_like_backtest(tmp_path: Path) -> None:
    from ibtrader.execution.rebalance import ProposedOrder
    from ibtrader.ops.run_daily import settled_after, unchanged_targets

    book = {"shares": {"SPY": 10, "IEF": 5}, "last_targets": {"SPY": 0.3, "IEF": 0.3}, "settled": ["SPY", "IEF"]}
    assert unchanged_targets({"SPY": 0.3, "IEF": 0.25, "GLD": 0.1}, book) == ["SPY"]
    assert unchanged_targets({"SPY": 0.3}, {"shares": {"SPY": 10}}) == []  # first plan trades
    # A clipped order (max notional) leaves the symbol unsettled → it keeps building the next day.
    clipped = ProposedOrder("SPY", "BUY", 19, 500.0, 0.3, 0, 30, notes=["clipped_from=30"])
    assert settled_after({"SPY": 0.3, "IEF": 0.3}, [clipped], [clipped], []) == ["IEF"]
    assert unchanged_targets({"SPY": 0.3}, {**book, "settled": ["IEF"]}) == []


def test_cash_etf_exempt_from_weight_cap_and_reductions_go_first() -> None:
    from ibtrader.config import PretradeConfig
    from ibtrader.execution.rebalance import ProposedOrder
    from ibtrader.risk.pretrade import PretradeContext, check_orders

    cfg = PretradeConfig(max_order_notional_usd=1e9)
    px = {"SPY": 100.0, "BIL": 100.0}
    buy_bil = ProposedOrder("BIL", "BUY", 900, 100.0, 0.9, 0, 900)
    sell_spy = ProposedOrder("SPY", "SELL", 900, 100.0, 0.0, 900, 0)
    ctx = PretradeContext(nav=100_000.0, positions={"SPY": 900}, prices=px, cash_symbols=["BIL"])
    dec = check_orders([buy_bil, sell_spy], ctx, cfg)  # buy listed first on purpose
    assert [o.symbol for o in dec.approved] == ["SPY", "BIL"] and not dec.rejected
    ctx2 = PretradeContext(nav=100_000.0, positions={"SPY": 900}, prices=px)
    assert any("max_weight" in r for _, r in check_orders([buy_bil, sell_spy], ctx2, cfg).rejected)


def test_stale_symbol_is_held_not_sold(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    frames = _frames()
    frames["IEF"] = frames["IEF"].iloc[:-1]  # IEF's provider is a day late
    rep = run_plan(s, loader=lambda _s: frames, now=PLAN_AT)
    assert all(o["symbol"] != "IEF" for o in rep["pretrade"]["approved"])
    assert rep["targets"]["meta"]["stale_symbols"] == ["IEF"] and "IEF" not in rep["targets"]["weights"]


def test_dividend_cash_between_plan_and_execute_is_not_a_break(tmp_path: Path) -> None:
    from ibtrader.ops.reconcile import reconcile

    r = reconcile({"cash": 1000.0, "shares": {"VNQ": 100}}, {"VNQ": 100}, 1310.0,
                  cash_tolerance_usd=25.0, cash_surplus_tolerance_usd=500.0)
    assert r.ok and r.warnings
    short = reconcile({"cash": 1000.0, "shares": {}}, {}, 600.0, cash_tolerance_usd=25.0,
                      cash_surplus_tolerance_usd=500.0)
    assert not short.ok  # missing cash is always a break


def test_crashed_execute_is_never_resent(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    pend = tmp_path / "data" / "pending_orders.json"
    raw = json.loads(pend.read_text())
    raw["execution_started_at"] = "2026-11-10T14:40:00+00:00"  # died after sending
    pend.write_text(json.dumps(raw))
    broker = Broker({"SPY": 5}, 47_000.0)
    ex = run_execute(s, gateway_factory=lambda _s: broker, now=EXEC_AT)
    assert ex["status"] == "resumed_after_crash" and broker.orders == {}
    book = json.loads((tmp_path / "data" / "paper_account.json").read_text())
    assert book["shares"] == {"SPY": 5} and (tmp_path / "data" / "pending_orders.interrupted.json").exists()


def test_gateway_down_is_alerted_not_crashed(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)

    def down(_s):
        raise ConnectionRefusedError("IB Gateway not running")

    ex = run_execute(s, gateway_factory=down, now=EXEC_AT)
    assert ex["status"] == "broker_error"
    assert "broker_unreachable" in (tmp_path / "data" / "alerts.jsonl").read_text()
    assert (tmp_path / "data" / "pending_orders.json").exists()  # nothing consumed


def test_fresh_loader_bypasses_cache_without_touching_settings(monkeypatch) -> None:
    import ibtrader.data.service as svc
    from ibtrader.ops.run_daily import fresh_loader

    seen = {}
    monkeypatch.setattr(svc, "load_universe_v2", lambda st: seen.setdefault("use_cache", st.engine.use_cache) and {})
    s = AppSettings(_env_file=None)
    s.engine.use_cache = True
    fresh_loader(s)
    assert seen["use_cache"] is False and s.engine.use_cache is True


def test_shadow_fill_uses_backtest_cost_model() -> None:
    from datetime import date as _date

    from ibtrader.ops.run_daily import shadow_fill

    s = AppSettings(_env_file=None)
    buy = shadow_fill(s, "SPY", "BUY", 100, 500.0, _date(2026, 11, 9))
    sell = shadow_fill(s, "SPY", "SELL", 100, 500.0, _date(2026, 11, 9))
    assert buy.price > 500.0 > sell.price  # half spread paid both ways
    assert sell.cost > buy.cost > 0  # SEC/FINRA fees only on sells


def test_loss_limits_match_backtest_risk_manager(tmp_path: Path) -> None:
    from ibtrader.ops.paper_curve import append_daily_equity_point
    from ibtrader.ops.run_daily import loss_limit_blocks

    s = AppSettings(_env_file=None)
    p = tmp_path / "eq.jsonl"
    for i, eq in enumerate([100_000, 110_000, 95_000, 86_000]):
        append_daily_equity_point(p, eq, f"2026-11-0{i + 2}", basis="shadow")
    blocks = loss_limit_blocks(p, s)
    assert any(b.startswith("drawdown_limit") for b in blocks)  # 86k vs 110k peak = -21.8 %
    assert any(b.startswith("daily_loss_limit") for b in blocks)  # 95k → 86k = -9.5 %
    assert not any(b.startswith("cumulative") for b in blocks)  # -14 % vs first point


def test_freeze_catches_universe_file_edits(tmp_path: Path) -> None:
    from ibtrader.ops.config_freeze import verify_freeze

    uni = tmp_path / "uni.json"
    uni.write_text('{"name": "u", "symbols": []}')
    s = _settings(tmp_path)
    s.data.universe_file = str(uni)
    f = tmp_path / "freeze.json"
    write_freeze(f, s)
    assert verify_freeze(f, s)["ok"] is True
    uni.write_text('{"name": "u2", "symbols": []}')  # e.g. a box moved
    v = verify_freeze(f, s)
    assert v["ok"] is False and "universe_spec" in v["changed_sections"]


def test_rejected_strategy_never_reaches_the_broker(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    s.strategy.name = "sma_crossover"
    s.strategy.params = {"fast_window": 10, "slow_window": 30}
    write_freeze(tmp_path / "data" / "paper_config_freeze.json", s)
    rep = run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    assert "strategy_rejected: sma_crossover" in rep["blocks"] and rep["pretrade"]["n_approved"] == 0
    assert "risk_restricted" in rep["pretrade"]["global_blocks"]


def test_execute_on_a_holiday_keeps_pending(tmp_path: Path) -> None:
    s = _orders_ready(tmp_path)
    run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    broker = Broker({}, 50_000.0)
    pre_open = datetime(2026, 11, 10, 8, 0, tzinfo=ET)
    ex = run_execute(s, gateway_factory=lambda _s: broker, now=pre_open)
    assert ex["status"] == "market_closed" and broker.orders == {}
    assert (tmp_path / "data" / "pending_orders.json").exists()


def test_cli_crash_raises_critical_alert(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    import ibtrader.ops.run_daily as rd
    from ibtrader.ops.cli import app

    monkeypatch.setenv("OPS__ALERTS_FILE", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("DATA__DATA_DIR", str(tmp_path / "data"))

    def boom(*_a, **_k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(rd, "run_plan", boom)
    r = CliRunner().invoke(app, ["run-daily", "--phase", "plan"])
    assert r.exit_code == 2
    assert "run_daily_crash" in (tmp_path / "alerts.jsonl").read_text()


def test_copilot_opinion_is_recorded_and_never_changes_orders(tmp_path: Path, monkeypatch) -> None:
    from ibtrader.intelligence import copilot as cp

    base = run_plan(_settings(tmp_path / "a"), loader=lambda _s: _frames(), now=PLAN_AT)
    s = _settings(tmp_path / "b")
    s.ops.copilot = True
    op = cp.Opinion(summary="Compra acciones y bonos.", risks=[],
                    views=[cp.SymbolView(symbol="SPY", stance="reducir", conviction=3, reason="x")])
    monkeypatch.setattr(cp, "daily_opinion", lambda *a, **k: op)
    rep = run_plan(s, loader=lambda _s: _frames(), now=PLAN_AT)
    assert rep["status"] == "ok" and rep["copilot"]["status"] == "ok"
    assert rep["pretrade"]["approved"] == base["pretrade"]["approved"]
    row = json.loads((tmp_path / "b" / "data" / "copilot_opinions.jsonl").read_text().splitlines()[0])
    assert row["tilted"]["SPY"] < row["weights"]["SPY"] and row["closes"]["SPY"] > 0
    # Sin puerta ni opinión, la corrida sigue igual.
    monkeypatch.setattr(cp, "daily_opinion", lambda *a, **k: None)
    s2 = _settings(tmp_path / "c")
    s2.ops.copilot = True
    rep2 = run_plan(s2, loader=lambda _s: _frames(), now=PLAN_AT)
    assert rep2["status"] == "ok" and rep2["copilot"] == {"status": "sin_opinion"}
