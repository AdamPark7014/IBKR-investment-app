"""The daily production run in two phases (audit 2026-11-07, §5).

``plan`` (after the close, ~19:00 ET once Tiingo has published):
  data → freshness / cross-source → freeze check → target weights → loss limits (same as the backtest RiskManager) →
  orders toward targets → pre-trade gate → (shadow) simulated fills into the paper book, or
  (orders modes) ``data/pending_orders.json`` for the next open → equity point → heartbeat.

``execute`` (next session, ~09:35 ET, orders modes only):
  pending orders from the last session only → execution permission → broker account check →
  book vs broker reconciliation BEFORE trading → pre-trade globals again (kill switch may have
  appeared overnight) → ``OrderManager`` → reconciliation AFTER trading → book := broker.

Fail-closed everywhere: any exception or failed check ends in "no new risk" plus an alert; a
broken reconciliation also writes the kill switch. Claude (``OPS__AI_TRIAGE``) may annotate a
critical alert, never change what happens.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from ..config import AppSettings
from ..data.crosscheck import check_freshness, cross_check, last_completed_session
from ..engine.targets import compute_target_weights
from ..execution.order_manager import ManagedOrder, OrderGateway, OrderManager, execution_permission
from ..execution.rebalance import ProposedOrder, build_rebalance_orders
from ..risk.pretrade import PretradeContext, check_orders
from .config_freeze import verify_freeze
from .killswitch import activate_killswitch
from .notify import emit_alert, write_heartbeat
from .paper_curve import append_daily_equity_point, load_equity_points
from .reconcile import Fill, apply_fills, load_book, reconcile, save_book

Loader = Callable[[AppSettings], Mapping[str, pd.DataFrame]]
GatewayFactory = Callable[[AppSettings], OrderGateway]

log = logging.getLogger(__name__)


@dataclass
class Paths:
    book: Path
    equity: Path
    pending: Path
    orders: Path
    slippage: Path
    freeze: Path
    reports: Path

    @classmethod
    def from_settings(cls, s: AppSettings) -> "Paths":
        d = Path(s.data.data_dir)
        return cls(
            book=d / "paper_account.json",
            equity=d / "paper_equity.jsonl",
            pending=d / "pending_orders.json",
            orders=d / "orders.jsonl",
            slippage=d / "slippage_ledger.jsonl",
            freeze=d / "paper_config_freeze.json",
            reports=Path(s.data.reports_dir) / "daily",
        )


# --------------------------------------------------------------------------- helpers
def raw_last_prices(data: Mapping[str, pd.DataFrame]) -> Dict[str, float]:
    """Last *unadjusted* close (orders and NAV use real prices, not total-return-adjusted ones)."""
    out: Dict[str, float] = {}
    for sym, df in data.items():
        if df is None or len(df) == 0:
            continue
        col = "close_raw" if "close_raw" in df.columns else "close"
        v = float(df[col].iloc[-1])
        if v > 0 and math.isfinite(v):
            out[sym] = v
    return out


def book_nav(book: Mapping[str, Any], prices: Mapping[str, float]) -> float:
    shares = dict(book.get("shares") or {})
    missing = [s for s, q in shares.items() if int(q) != 0 and s not in prices]
    if missing:
        return float("nan")
    return float(book.get("cash") or 0.0) + sum(int(q) * float(prices[s]) for s, q in shares.items())


def unchanged_targets(weights: Mapping[str, float], book: Mapping[str, Any]) -> List[str]:
    """Symbols whose target weight did not move since the last plan and that are already held.

    Same rule as the backtest's weight mode (``backtest.engine``): a held position is only traded
    when its target weight changes, never on price drift. Without it production would turn over
    more than the research that approved it (and pay costs research never saw).
    """
    last = dict(book.get("last_targets") or {})
    settled = set(book.get("settled") or [])
    shares = dict(book.get("shares") or {})
    return [s for s, w in weights.items()
            if s in last and s in settled and int(shares.get(s, 0) or 0) != 0
            and abs(float(w) - float(last[s])) < 1e-9]


def settled_after(weights: Mapping[str, float], orders: Sequence[ProposedOrder],
                  approved: Sequence[ProposedOrder], stale: Sequence[str]) -> List[str]:
    """Symbols that will sit at their target once the approved orders fill.

    A clipped (``max_order_notional``) or rejected order leaves its symbol unsettled, so the next
    plan keeps trading toward the target even if the weight did not move.
    """
    ok = {o.symbol for o in approved if not o.notes}
    touched = {o.symbol for o in orders}
    return sorted(s for s in weights if s not in stale and (s not in touched or s in ok))


def cash_symbols_of(symbols: Sequence[str], spec: Any = None) -> List[str]:
    """Cash-equivalent ETFs among ``symbols``: box ``cash`` in the universe file, else a known T-bill ETF."""
    from ..pipeline.system import KNOWN_CASH_ETFS

    boxes = {e.symbol: e.box for e in spec.entries} if spec is not None else {}
    return [s for s in symbols if boxes.get(s) == "cash" or (s not in boxes and s.upper() in KNOWN_CASH_ETFS)]



def loss_limit_blocks(equity_path: Path, settings: AppSettings) -> List[str]:
    """The backtest's ``RiskManager`` limits, on the paper equity curve (research ↔ production parity).

    Same three rules the research backtest applied to the strategy it approved, re-checked every
    session and lifted when the condition clears: drawdown from peak, cumulative loss from the first
    point, and a daily loss on the last session (restricts the next day, as ``halt_next_day``).
    Each one blocks risk increases; reductions and exits still go through.
    """
    pts = [float(p["equity"]) for p in load_equity_points(equity_path) if p.get("equity") is not None]
    pts = [p for p in pts if p > 0]
    if len(pts) < 2:
        return []
    r = settings.risk
    out: List[str] = []
    dd = pts[-1] / max(pts) - 1.0
    if dd < -r.drawdown_limit_pct / 100.0:
        out.append(f"drawdown_limit: {dd:.1%} < -{r.drawdown_limit_pct:g}%")
    cum = pts[-1] / pts[0] - 1.0
    if cum < -r.cumulative_loss_limit_pct / 100.0:
        out.append(f"cumulative_loss_limit: {cum:.1%} < -{r.cumulative_loss_limit_pct:g}%")
    day = pts[-1] / pts[-2] - 1.0
    if day < -r.daily_loss_limit_pct / 100.0:
        out.append(f"daily_loss_limit: {day:.1%} < -{r.daily_loss_limit_pct:g}%")
    return out


def credit_corporate_actions(
    book: Dict[str, Any], data: Mapping[str, pd.DataFrame], since: Optional[date], until: date
) -> List[Dict[str, Any]]:
    """Dividends (and splits) for the shadow book, from the adjusted vs raw close of each bar.

    A holder's total return on a bar is ``close_t / close_{t-1}`` (adjusted). The cash dividend per
    share that reconciles it with the raw prices is ``D = a · raw_{t-1} − raw_t``. A ratio
    ``a / r`` far from 1 (raw moved ×2 or ×½ while the adjusted price did not) is a split: shares
    are scaled and rounded down. Without a separate ``close_raw`` column nothing is credited.
    Mutates ``book``; returns one event per credit.
    """
    events: List[Dict[str, Any]] = []
    if since is None:
        return events
    shares = book.setdefault("shares", {})
    for sym, q in list(shares.items()):
        df = data.get(sym)
        if not q or df is None or "close_raw" not in df.columns or len(df) < 2:
            continue
        adj, raw = df["close"].astype(float), df["close_raw"].astype(float)
        days = [d for d in df.index if since < pd.Timestamp(d).date() <= until]
        for d in days:
            i = df.index.get_loc(d)
            if not isinstance(i, int) or i == 0:
                continue
            a = adj.iloc[i] / adj.iloc[i - 1]
            r = raw.iloc[i] / raw.iloc[i - 1]
            if not (math.isfinite(a) and math.isfinite(r) and a > 0 and r > 0):
                continue
            k = a / r
            if k > 1.4 or k < 0.7:
                k = float(Fraction(k).limit_denominator(10))  # 2:1, 3:2, 1:4 ... (data carries rounding noise)
                new_q = int(math.floor(int(shares[sym]) * k + 1e-9))
                events.append({"date": str(pd.Timestamp(d).date()), "symbol": sym, "split": round(k, 4),
                               "shares_before": int(shares[sym]), "shares_after": new_q})
                shares[sym] = new_q
                continue
            div = a * raw.iloc[i - 1] - raw.iloc[i]
            if div > 1e-6 * raw.iloc[i - 1]:
                cash = float(div) * int(shares[sym])
                book["cash"] = float(book.get("cash") or 0.0) + cash
                events.append({"date": str(pd.Timestamp(d).date()), "symbol": sym,
                               "dividend_per_share": round(float(div), 6), "cash": round(cash, 2)})
    return events


def drawdown_now(equity_path: Path) -> Optional[float]:
    pts = [float(p["equity"]) for p in load_equity_points(equity_path) if p.get("equity") is not None]
    if len(pts) < 2:
        return None
    peak = max(pts)
    return pts[-1] / peak - 1.0 if peak > 0 else None


def estimate_cost(settings: AppSettings, symbol: str, qty: int, price: float) -> float:
    """Commission for ``qty`` shares at ``price`` with the configured IBKR schedule (fixed or tiered)."""
    from ..execution.costs import commission

    return float(commission(settings.commission, int(qty), float(price)))


def shadow_fill(settings: AppSettings, symbol: str, side: str, qty: int, price: float, trade_date: date,
                df: Optional[pd.DataFrame] = None) -> Fill:
    """Shadow fill with the backtest's own cost model (``execution.costs.total_order_cost``):
    half spread + square-root impact (when ADV/σ are known) in the price, commission + SEC/FINRA
    fees in cash. Research and paper therefore charge the same costs."""
    from ..execution.costs import rolling_adv_and_sigma, total_order_cost

    sigma = adv = None
    if df is not None and len(df) > 2:
        a, sg = rolling_adv_and_sigma(df, settings.slippage.adv_window_days, settings.slippage.sigma_window_days)
        last_a, last_s = float(a.iloc[-1]), float(sg.iloc[-1])
        adv = last_a if math.isfinite(last_a) and last_a > 0 else None
        sigma = last_s if math.isfinite(last_s) and last_s > 0 else None
    signed = int(qty) if side == "BUY" else -int(qty)
    oc = total_order_cost(symbol, signed, float(price), trade_date, commission_cfg=settings.commission,
                          slippage_cfg=settings.slippage, reg_fees_cfg=settings.reg_fees,
                          sigma_daily=sigma, adv_shares=adv)
    return Fill(symbol, side, int(qty), float(oc.fill_price), float(oc.explicit_fees))



def _alert(settings: AppSettings, report: Dict[str, Any], code: str, sev: str, msg: str,
           ctx: Optional[Mapping[str, Any]] = None) -> None:
    context = dict(ctx or {})
    if sev == "critical" and settings.ops.ai_triage:
        from ..intelligence.triage import triage_incident

        t = triage_incident(
            {"code": code, "message": msg, "phase": report.get("phase"), "mode": report.get("mode"),
             "blocks": report.get("blocks"), "context": context},
            data_dir=settings.data.data_dir, budget_usd=settings.ops.ai_monthly_budget_usd,
            model=settings.ops.ai_model,
        )
        if t is not None:
            context["ai_triage"] = t.model_dump()
    report.setdefault("alerts", []).append(emit_alert(settings.ops, code, sev, msg, context))


def _save_report(paths: Paths, report: Dict[str, Any]) -> None:
    paths.reports.mkdir(parents=True, exist_ok=True)
    name = f"{report.get('run_date') or 'unknown'}-{report['phase']}.json"
    (paths.reports / name).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                      encoding="utf-8")
    report["report_path"] = str(paths.reports / name)


def _proposed_from_dict(d: Mapping[str, Any]) -> ProposedOrder:
    keys = ("symbol", "side", "quantity", "ref_price", "target_weight", "current_qty", "target_qty",
            "limit_price", "is_exit", "notes")
    return ProposedOrder(**{k: d[k] for k in keys if k in d})


# --------------------------------------------------------------------------- plan
def run_plan(
    settings: AppSettings,
    *,
    loader: Loader,
    secondary_loader: Optional[Loader] = None,
    gateway_factory: Optional[GatewayFactory] = None,
    now: Optional[datetime] = None,
    spec: Any = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    paths = Paths.from_settings(settings)
    session = last_completed_session(now)
    mode = settings.execution.mode
    report: Dict[str, Any] = {"phase": "plan", "run_date": session.isoformat(), "mode": mode,
                              "started_at": now.isoformat(), "orders_sent": 0, "blocks": [], "status": "ok"}
    try:
        data = dict(loader(settings))
    except Exception as exc:  # noqa: BLE001
        report["status"] = "data_error"
        _alert(settings, report, "data_load", "critical", f"{type(exc).__name__}: {exc}")
        _save_report(paths, report)
        return report

    fresh = check_freshness(data, now)
    report["freshness"] = fresh.to_dict()
    data_ok = fresh.ok
    if secondary_loader is not None:
        try:
            cross = cross_check(data, dict(secondary_loader(settings)))
            report["cross_check"] = cross.to_dict()
            data_ok = data_ok and cross.ok
        except Exception as exc:  # noqa: BLE001 - a missing second source warns, does not block
            report["cross_check"] = {"ok": None, "error": f"{type(exc).__name__}: {exc}"}
    if not data_ok:
        report["blocks"].append("data")
        _alert(settings, report, "data_quality", "warn", "; ".join(fresh.reasons + report.get("cross_check", {})
                                                                  .get("reasons", [])))

    freeze = verify_freeze(paths.freeze, settings)
    report["freeze"] = {k: freeze.get(k) for k in ("ok", "reason", "changed_sections")}
    # Orders must come from the frozen system. Shadow only warns, so the paper curve can start
    # before the first freeze (the freeze is then written once the research verdict exists).
    freeze_ok = bool(freeze.get("ok")) or mode == "shadow"
    if not freeze.get("ok"):
        if mode == "shadow":
            report["warnings"] = [f"freeze:{freeze.get('reason')} (modo sombra: no bloquea)"]
        else:
            report["blocks"].append(f"freeze:{freeze.get('reason')}")

    if spec is None and settings.data.universe_file:
        from ..data.universe import load_universe_spec

        spec = load_universe_spec(settings.data.universe_file)
    weights, meta = compute_target_weights(settings, data, spec)
    report["targets"] = {"weights": weights, "meta": meta}
    if meta.get("legacy"):
        # sma_crossover was rejected by research: it may feed the shadow book, never the broker.
        if mode == "shadow":
            report.setdefault("warnings", []).append("sma_crossover fue rechazada por la investigación (solo sombra)")
        else:
            report["blocks"].append("strategy_rejected: sma_crossover")
            freeze_ok = False  # same effect as an invalid freeze: nothing new reaches the broker

    report["drawdown"] = drawdown_now(paths.equity)
    loss_blocks = loss_limit_blocks(paths.equity, settings)
    risk_can_increase = not loss_blocks
    if loss_blocks:
        report["blocks"].extend(loss_blocks)
        _alert(settings, report, "loss_limit", "critical", "; ".join(loss_blocks) + ": solo reducciones")

    prices = raw_last_prices(data)
    book = load_book(paths.book)
    if book is None:
        if mode == "shadow":
            book = {"cash": float(settings.pretrade.capital_usd or 100_000.0), "shares": {},
                    "basis": "shadow", "initialized": now.isoformat()}
            report["book_initialized"] = True
        elif gateway_factory is not None:
            shares, cash, acct = gateway_factory(settings).account_snapshot()
            book = {"cash": float(cash or 0.0), "shares": shares, "basis": "broker", "account": acct}
            report["book_initialized"] = "from_broker"
        else:
            report["status"] = "book_missing"
            _alert(settings, report, "book_missing", "critical", "sin paper_account.json ni broker")
            _save_report(paths, report)
            return report
    if book.get("basis") == "shadow":
        last = book.get("last_session")
        report["corporate_actions"] = credit_corporate_actions(
            book, data, date.fromisoformat(last) if last else None, session)
    nav = book_nav(book, prices)
    report["nav_before"] = nav
    stale = list(meta.get("stale_symbols") or [])
    invest_nav = nav * (1.0 - settings.pretrade.cash_buffer_pct / 100.0)
    orders = build_rebalance_orders(
        weights, dict(book.get("shares") or {}), prices, invest_nav,
        min_notional=settings.pretrade.min_order_notional_usd,
        max_notional=settings.pretrade.max_order_notional_usd,
        hold=stale + [s for s in (book.get("shares") or {}) if s not in data]
        + unchanged_targets(weights, book),
    )
    if meta.get("stale_symbols"):
        report.setdefault("warnings", []).append(f"se mantienen sin operar (sin barra de hoy): {meta['stale_symbols']}")
    as_of = pd.Timestamp(meta.get("as_of")).date() if meta.get("as_of") else None
    ctx = PretradeContext(
        nav=nav, positions=dict(book.get("shares") or {}), prices=prices,
        allowed_symbols=list(settings.universe.symbols), allow_short=settings.trading.allow_short,
        killswitch_active=Path(settings.risk.killswitch_file).exists(), account_ok=True,
        data_fresh=data_ok, risk_can_increase=risk_can_increase and freeze_ok,
        reference_date=as_of, today=session, cash_symbols=cash_symbols_of(list(weights), spec),
    )
    dec = check_orders(orders, ctx, settings.pretrade)
    report["pretrade"] = dec.to_dict()
    settled = settled_after(weights, orders, dec.approved, stale)

    if mode == "shadow":
        mgr = OrderManager(None, settings.execution, ledger_path=paths.orders)
        mgr.execute(dec.approved, session, send=False)
        fills = []
        for o in dec.approved:
            fills.append(shadow_fill(settings, o.symbol, o.side, o.quantity, o.ref_price, session, data.get(o.symbol)))
        book = apply_fills(book, fills)
        book["basis"] = "shadow"
        book["last_session"] = session.isoformat()
        book["last_targets"] = {s: float(w) for s, w in weights.items()}
        book["settled"] = settled
        save_book(paths.book, book)
        report["shadow_fills"] = [f.__dict__ for f in fills]
        report["note"] = ("sombra: ejecuta al cierre con el modelo de costes del backtest (medio spread + impacto, "
                          "comisión + tasas SEC/FINRA); sin cola ni ejecuciones parciales: aún optimista")
    else:
        paths.pending.parent.mkdir(parents=True, exist_ok=True)
        paths.pending.write_text(json.dumps(
            {"run_date": session.isoformat(), "created_at": now.isoformat(), "mode": mode,
             "targets": {s: float(w) for s, w in weights.items()}, "settled_if_filled": settled,
             "orders": [o.to_dict() for o in dec.approved]}, indent=2, default=str), encoding="utf-8")
        report["pending_orders"] = str(paths.pending)

    nav_after = book_nav(book, prices)
    report["nav_after"] = nav_after
    if math.isfinite(nav_after):
        append_daily_equity_point(paths.equity, nav_after, session.isoformat(), basis=str(book.get("basis")))
    if settings.ops.copilot:
        report["copilot"] = copilot_opinion(settings, session, weights, book, prices, data, report, paths)
    if report["blocks"]:
        report["status"] = "blocked_new_risk"
    write_heartbeat(settings.ops, {"phase": "plan", "run_date": session.isoformat(), "status": report["status"],
                                   "n_orders": len(dec.approved), "mode": mode}, now=now)
    _save_report(paths, report)
    return report


def copilot_opinion(settings: AppSettings, session: date, weights: Mapping[str, float], book: Mapping[str, Any],
                    prices: Mapping[str, float], data: Mapping[str, pd.DataFrame], report: Mapping[str, Any],
                    paths: Any) -> Dict[str, Any]:
    """Opinión de Claude en sombra: se registra y se mide, nunca toca el plan ni las órdenes."""
    from ..intelligence.copilot import COPILOT_MODEL, build_facts, daily_opinion, record_opinion

    try:
        nav = book_nav(book, prices)
        shares = dict(book.get("shares") or {})
        current = {s: float(q) * float(prices.get(s, 0.0)) / nav for s, q in shares.items()} if nav > 0 else {}
        closes = {s: [float(x) for x in df["close"].astype(float).tail(64)] for s, df in data.items()
                  if s in weights and "close" in df.columns}
        alerts = [str(a.get("code")) for a in report.get("alerts") or [] if isinstance(a, Mapping)]
        facts = build_facts(session.isoformat(), weights, current, closes, drawdown_now(paths.equity), alerts)
        model = settings.ops.ai_model or COPILOT_MODEL
        op = daily_opinion(facts, data_dir=settings.data.data_dir, budget_usd=settings.ops.ai_monthly_budget_usd,
                           model=model)
        if op is None:
            return {"status": "sin_opinion"}
        last_close = {s: c[-1] for s, c in closes.items() if c}
        record_opinion(Path(settings.data.data_dir) / "copilot_opinions.jsonl", session.isoformat(), weights,
                       last_close, op, model=model)
        return {"status": "ok", **op.model_dump()}
    except Exception as exc:  # noqa: BLE001 - el copiloto nunca rompe la corrida diaria
        log.warning("copilot_failed %s: %s", type(exc).__name__, exc)
        return {"status": f"error:{type(exc).__name__}"}


# --------------------------------------------------------------------------- execute
def run_execute(
    settings: AppSettings,
    *,
    gateway_factory: GatewayFactory,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    paths = Paths.from_settings(settings)
    report: Dict[str, Any] = {"phase": "execute", "mode": settings.execution.mode, "started_at": now.isoformat(),
                              "orders_sent": 0, "blocks": [], "status": "ok"}
    if settings.execution.mode == "shadow":
        report["status"] = "shadow_nothing_to_execute"
        return report
    if not paths.pending.is_file():
        report["status"] = "no_pending_orders"
        return report
    pending = json.loads(paths.pending.read_text(encoding="utf-8"))
    run_date = date.fromisoformat(str(pending.get("run_date")))
    report["run_date"] = run_date.isoformat()
    expected = last_completed_session(now)
    if run_date != expected:
        report["status"] = "pending_stale"
        _alert(settings, report, "pending_stale", "warn",
               f"órdenes pendientes del {run_date} pero la última sesión es {expected}: no se ejecutan")
        paths.pending.rename(paths.pending.with_suffix(".stale.json"))
        _save_report(paths, report)
        return report

    from ..execution.session import is_rth

    if not is_rth(now):
        # Holiday, weekend or outside 09:30-16:00 ET: DAY orders would be rejected or wait for a
        # stale open. Leave the pending file for the next session (the next plan replaces it).
        report["status"] = "market_closed"
        _save_report(paths, report)
        return report
    open_et = now.astimezone(ZoneInfo("America/New_York")).replace(hour=9, minute=30, second=0, microsecond=0)
    if now < open_et + timedelta(minutes=settings.execution.min_minutes_after_open):
        # Los spreads de los ETF son más anchos en la subasta y los primeros minutos (patrón en U
        # intradía); esperar media hora abarata cada orden sin cambiar la señal.
        report["status"] = "too_early"
        _save_report(paths, report)
        return report

    ok, why = execution_permission(settings)
    if not ok:
        report["status"] = "not_permitted"
        _alert(settings, report, "execution_not_permitted", "critical", why)
        _save_report(paths, report)
        return report

    try:
        gw = gateway_factory(settings)
        shares, cash, acct = gw.account_snapshot()
    except Exception as exc:  # noqa: BLE001 - Gateway down / login expired: alert, send nothing
        report["status"] = "broker_error"
        _alert(settings, report, "broker_unreachable", "critical", f"{type(exc).__name__}: {exc}")
        _save_report(paths, report)
        return report
    exp_acct = (settings.ib.expected_account or "").strip()
    account_ok = (not exp_acct) or acct == exp_acct
    book = load_book(paths.book) or {"cash": float(cash or 0.0), "shares": shares, "basis": "broker"}
    if pending.get("execution_started_at"):
        # A previous execute died after sending orders. Never send them again: adopt the broker
        # state as the book, park the pending file and ask for a human look.
        save_book(paths.book, {"cash": float(cash or 0.0), "shares": shares, "basis": "broker", "account": acct,
                               "synced_at": now.isoformat(), "last_targets": dict(pending.get("targets") or {}),
                               "settled": []})
        paths.pending.rename(paths.pending.with_suffix(".interrupted.json"))
        report["status"] = "resumed_after_crash"
        _alert(settings, report, "execute_interrupted", "critical",
               f"la ejecución del {run_date} empezó a las {pending['execution_started_at']} y no terminó: "
               "NO se reenviaron órdenes; libro sincronizado con el broker, revisa orders.jsonl")
        _save_report(paths, report)
        return report
    ref_px = {str(o.get("symbol")): float(o.get("ref_price") or 0.0) for o in pending.get("orders") or []}
    nav_hint = float(cash or 0.0) + sum(abs(q) * ref_px.get(s, 0.0) for s, q in shares.items())
    pre = reconcile(book, shares, cash, cash_tolerance_usd=max(25.0, 0.0005 * float(book.get("cash") or 0.0)),
                    cash_surplus_tolerance_usd=max(500.0, 0.01 * nav_hint))
    report["reconcile_before"] = pre.to_dict()
    if not pre.ok:
        activate_killswitch(settings.risk.killswitch_file)
        report["status"] = "reconcile_break_before"
        _alert(settings, report, "reconcile_break", "critical", "; ".join(pre.reasons), pre.to_dict())
        _save_report(paths, report)
        return report

    orders = [_proposed_from_dict(d) for d in pending.get("orders") or []]
    prices = {o.symbol: o.ref_price for o in orders}
    for s, q in shares.items():
        prices.setdefault(s, next((o.ref_price for o in orders if o.symbol == s), 0.0))
    ctx = PretradeContext(
        nav=float(cash or 0.0) + sum(q * prices.get(s, 0.0) for s, q in shares.items()),
        positions=shares, prices=prices, allowed_symbols=list(settings.universe.symbols),
        allow_short=settings.trading.allow_short, killswitch_active=Path(settings.risk.killswitch_file).exists(),
        account_ok=account_ok,
    )
    dec = check_orders(orders, ctx, settings.pretrade)
    report["pretrade"] = dec.to_dict()
    pending["execution_started_at"] = now.isoformat()
    paths.pending.write_text(json.dumps(pending, indent=2, default=str), encoding="utf-8")
    mgr = OrderManager(gw, settings.execution, ledger_path=paths.orders, slippage_path=paths.slippage)
    managed: List[ManagedOrder] = mgr.execute(dec.approved, run_date, send=True)
    report["orders"] = [m.to_dict() for m in managed]
    report["orders_sent"] = sum(1 for m in managed if m.broker_ids)

    fills = [Fill(m.symbol, m.side, m.filled_qty, m.avg_fill_price) for m in managed if m.filled_qty > 0]
    expected_book = apply_fills({"cash": cash, "shares": shares}, fills)
    shares2, cash2, _ = gw.account_snapshot()
    commissions_bound = 25.0 + sum(estimate_cost(settings, f.symbol, f.qty, f.price) * 2 for f in fills)
    post = reconcile(expected_book, shares2, cash2, cash_tolerance_usd=commissions_bound)
    report["reconcile_after"] = post.to_dict()
    if not post.ok:
        activate_killswitch(settings.risk.killswitch_file)
        report["status"] = "reconcile_break_after"
        _alert(settings, report, "reconcile_break", "critical", "; ".join(post.reasons), post.to_dict())
    save_book(paths.book, {"cash": float(cash2 or 0.0), "shares": shares2, "basis": "broker", "account": acct,
                           "synced_at": now.isoformat(), "last_targets": dict(pending.get("targets") or {}),
                           "settled": sorted(set(pending.get("settled_if_filled") or [])
                                             - {m.symbol for m in managed if m.state.value != "FILLED"})})
    paths.pending.rename(paths.pending.with_suffix(".done.json"))
    failed = [m for m in managed if m.state.value in ("REJECTED", "CANCELLED")]
    if failed:
        _alert(settings, report, "orders_not_filled", "warn",
               ", ".join(f"{m.symbol} {m.state.value}: {m.reason}" for m in failed))
    write_heartbeat(settings.ops, {"phase": "execute", "run_date": run_date.isoformat(), "status": report["status"],
                                   "orders_sent": report["orders_sent"]}, now=now)
    _save_report(paths, report)
    return report


# --------------------------------------------------------------------------- CLI helpers
#: run status → process exit code for the scheduler: 0 normal, 1 blocked safely, 2 needs a human.
_EXIT_OK = {"ok", "shadow_nothing_to_execute", "no_pending_orders", "market_closed", "too_early"}
_EXIT_SAFE_BLOCK = {"blocked_new_risk", "pending_stale", "not_permitted"}


def exit_code_for(status: str) -> int:
    if status in _EXIT_OK:
        return 0
    return 1 if status in _EXIT_SAFE_BLOCK else 2


def primary_provider(settings: AppSettings) -> Optional[str]:
    """First provider that ``load_universe_v2`` will really try (Tiingo without token is skipped)."""
    for raw in settings.data.providers:
        name = raw.strip().lower()
        if name == "tiingo" and not settings.data.tiingo_token.strip():
            continue
        return name
    return None


def fresh_loader(settings: AppSettings) -> Mapping[str, pd.DataFrame]:
    """``load_universe_v2`` that never serves the cache: the daily run needs today's bar, and the
    cache accepts bars up to ``max_cache_age_days`` old (fine for research, a block every day here).
    Works on a copy so the frozen settings are untouched; the fresh download still refreshes the cache.
    """
    from ..data.service import load_universe_v2

    s = settings.model_copy(deep=True)
    s.engine.use_cache = False
    return load_universe_v2(s)


def secondary_loader_for(settings: AppSettings) -> Optional[Loader]:
    """An independent second source for the cross-check: Yahoo when the primary is not Yahoo.

    Reads providers directly (no cache, no vintage write), so it can never overwrite the primary's data.
    """
    primary = primary_provider(settings)
    if primary in (None, "yahoo", "fixture"):
        return None

    def load(s: AppSettings) -> Mapping[str, pd.DataFrame]:
        from ..data.providers import YahooProvider

        prov = YahooProvider()
        out: Dict[str, pd.DataFrame] = {}
        for sym in s.universe.symbols:
            try:
                out[sym] = prov.fetch_daily_ohlcv(sym).data
            except Exception:  # noqa: BLE001 - a missing secondary is reported by cross_check
                continue
        return out

    return load


__all__ = [
    "Paths", "book_nav", "cash_symbols_of", "credit_corporate_actions", "drawdown_now", "exit_code_for",
    "fresh_loader", "loss_limit_blocks", "primary_provider", "raw_last_prices", "run_execute", "run_plan",
    "secondary_loader_for",
    "settled_after", "shadow_fill", "unchanged_targets",
]
