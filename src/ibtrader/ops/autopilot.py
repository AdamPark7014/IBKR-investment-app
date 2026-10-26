"""Autopilot: heavy backend triage + one-screen UI. Zero broker orders, never LIVE."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..config import AppSettings
from ..data.service import load_universe_v2
from ..engine.decision import DecisionEngine
from ..execution.passive_aggressive import decide_urgency
from ..intelligence.brief import ai_brief, compress_facts
from ..intelligence.market_radar import build_market_radar
from ..intelligence.prompt_pack import PromptPack, default_pack
from .alerts import Alert, evaluate_paper_alerts
from .config_freeze import load_assumed_sharpe, verify_freeze
from .open_orders import load_touchable
from .paper_curve import (
    BASIS_CASH_SHARES,
    MIN_POINTS_FOR_KILL,
    REAL_BASES,
    account_equity,
    append_daily_equity_point,
    load_equity_points,
    load_paper_account,
    max_drawdown,
)
from .paper_vs_oos import compare_paper_vs_oos
from .shadow import desired_from_decisions, log_shadow_snapshot
from .simple_ui import write_simple_console
from .stack import PaperStack
from .urgency_age import load_open_order_age_seconds


def _load_held(path: Path) -> Dict[str, float]:
    """Held **weights** (fraction of NAV) for drift triage. Never valued as equity."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    return {}


def _slippage_summary(data_dir: Path, window_days: int = 30) -> Optional[Dict[str, Any]]:
    ledger = data_dir / "slippage_ledger.jsonl"
    if not ledger.is_file():
        return None
    try:
        from .slippage_ledger import summarize

        return summarize(ledger, window_days)
    except Exception:
        return None


def _last_prices(data: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for sym, df in (data or {}).items():
        try:
            if df is None or len(df) == 0 or not hasattr(df, "columns"):
                continue
            if "close" in df.columns:
                col = "close"
            elif len(df.columns):
                col = df.columns[0]
            else:
                continue
            out[str(sym)] = float(df[col].iloc[-1])
        except Exception:
            continue
    return out


def _freeze_alerts(freeze: Mapping[str, Any]) -> List[Alert]:
    reason = freeze.get("reason")
    if freeze.get("ok"):
        return []
    if reason == "missing_freeze":
        return [
            Alert(
                code="config_freeze_missing",
                severity="warn",
                message="no paper config freeze: run `ibtrader config-freeze --write` once when paper starts",
            )
        ]
    if reason == "freeze_schema_outdated":
        return [
            Alert(
                code="config_freeze_outdated",
                severity="warn",
                message="freeze predates mode/trading/strategy; same config — rewrite it with `config-freeze --write`",
            )
        ]
    changed = ", ".join(freeze.get("changed_sections") or []) or "unknown"
    return [
        Alert(
            code="config_drift",
            severity="kill_recommend",
            message=f"paper config differs from the freeze ({reason}; changed: {changed}) — do not retune live",
        )
    ]


def run_autopilot(
    settings: Optional[AppSettings] = None,
    *,
    use_ai: bool = False,
    pack: Optional[PromptPack] = None,
    open_ui: bool = False,
) -> Dict[str, Any]:
    """Pipeline: data → radar → paper shadow → brief → HTML. No broker orders."""
    s = settings or AppSettings()
    s.resolve_paths()
    data_dir = Path(s.data.data_dir)
    data = load_universe_v2(s)
    radar = build_market_radar(data)

    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    desired = desired_from_decisions(decisions)
    held_path = data_dir / "paper_positions.json"
    held = _load_held(held_path)
    paper = log_shadow_snapshot(desired, held, tag="autopilot")
    paper["orders_sent"] = 0
    paper["shadow_held_source"] = str(held_path) if held_path.exists() else None
    stack = PaperStack(data_dir / "paper_stack.sqlite")
    stack.sync_from_json(desired, held)
    stack_snap = stack.snapshot()
    paper_stack_info = {
        "n_drift": sum(1 for row in stack_snap.get("drift", []) if float(row.get("delta", 0)) != 0.0)
    }

    # Freeze is verified, never written here: a missing or changed freeze is reported, not re-baselined.
    freeze_path = data_dir / "paper_config_freeze.json"
    freeze = verify_freeze(freeze_path, s)

    open_orders_path = data_dir / "paper_open_orders.json"
    age_seconds = load_open_order_age_seconds(open_orders_path)
    touchable = load_touchable(open_orders_path)
    urgency = decide_urgency(age_seconds=age_seconds, max_passive_seconds=60.0, touchable=touchable)

    slip = _slippage_summary(data_dir)

    facts = compress_facts(
        radar=radar,
        paper=paper,
        slippage=slip,
        extra={
            "urgency_mode": urgency.mode,
            "urgency_reason": urgency.reason,
            "config_hash_ok": freeze.get("ok"),
            "config_freeze_reason": freeze.get("reason"),
            "config_hash": freeze.get("actual") or freeze.get("expected"),
        },
    )

    brief = ai_brief(facts, pack=pack or default_pack(), use_ai=use_ai)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(s.data.reports_dir) / "autopilot"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Paper equity: real money only (cash + shares from paper_account.json, or broker NAV). ---
    paper_equity_path = data_dir / "paper_equity.jsonl"
    account_path = data_dir / "paper_account.json"
    account = load_paper_account(account_path)
    equity_info: Dict[str, Any] = {
        "account_path": str(account_path),
        "account_present": account is not None,
        "equity": None,
        "missing_prices": [],
        "appended": False,
    }
    if account is not None:
        equity, missing = account_equity(account, _last_prices(data))
        equity_info["equity"] = equity
        equity_info["missing_prices"] = missing
        if equity is not None:
            day = str(radar.get("as_of") or datetime.now(timezone.utc).date().isoformat())
            equity_info["appended"] = append_daily_equity_point(
                paper_equity_path, equity, day=day, basis=BASIS_CASH_SHARES
            )
    real_points = load_equity_points(paper_equity_path, bases=REAL_BASES)
    n_real = len(real_points)
    kill_ready = n_real >= MIN_POINTS_FOR_KILL
    max_dd = max_drawdown([p["equity"] for p in real_points])
    equity_info.update({"n_real_points": n_real, "min_points_for_kill": MIN_POINTS_FOR_KILL,
                        "kill_alerts_active": kill_ready, "max_dd": max_dd})

    assumed = load_assumed_sharpe(freeze_path)
    paper_vs_oos = compare_paper_vs_oos(
        paper_max_dd=max_dd,
        paper_n_points=n_real,
        assumed_sharpe=assumed,
        min_points=MIN_POINTS_FOR_KILL,
    )

    alerts = evaluate_paper_alerts(
        max_drawdown=max_dd if kill_ready else None,
        assumed_sharpe=assumed,
        n_drift=int(paper_stack_info.get("n_drift") or 0),
        orders_sent=0,
    )
    if not kill_ready:
        alerts.append(
            Alert(
                code="paper_kill_alerts_inactive",
                severity="info",
                message=(
                    f"drawdown kill alerts off until {MIN_POINTS_FOR_KILL} daily points of real paper equity "
                    f"(cash+shares in paper_account.json or broker NAV); have {n_real}"
                ),
            )
        )
    alerts.extend(_freeze_alerts(freeze))
    if paper_vs_oos.get("kill_recommend"):
        alerts.append(
            Alert(
                code="paper_vs_oos_dd",
                severity="kill_recommend",
                message="paper DD vs OOS/Sharpe triage recommends kill — do not retune live",
            )
        )

    payload: Dict[str, Any] = {
        "exp_id": run_id,
        "phase": "autopilot-v1",
        "generated_at": run_id,
        "facts": facts,
        "brief": _build_brief_dict(brief),
        "radar": radar,
        "paper": paper,
        "orders_sent": 0,
        "disclaimer": facts.get("disclaimer"),
        "alerts": [{"code": a.code, "severity": a.severity, "message": a.message} for a in alerts],
        "config_freeze": freeze,
        "urgency": {"mode": urgency.mode, "reason": urgency.reason},
        "paper_stack": paper_stack_info,
        "paper_equity": equity_info,
        "paper_vs_oos": paper_vs_oos,
    }

    json_path = out_dir / f"autopilot_{run_id}.json"
    html_path = out_dir / f"autopilot_{run_id}.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_simple_console(payload, html_path, title="ibtrader")
    # latest pointers
    (out_dir / "latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    write_simple_console(payload, out_dir / "latest.html", title="ibtrader")

    payload["artifact_json"] = str(json_path)
    payload["artifact_html"] = str(html_path)
    payload["latest_html"] = str(out_dir / "latest.html")

    if open_ui:
        import webbrowser

        webbrowser.open(Path(html_path).resolve().as_uri())

    return payload


def _build_brief_dict(brief: Dict[str, Any]) -> Dict[str, Any]:
    base_keys = ("text", "source", "model", "pack")
    keys_to_use = [k for k in base_keys if k in brief]
    note_key = "note"
    if note_key in brief and "note" not in keys_to_use:
        keys_to_use.append(note_key)
    return {k: brief[k] for k in keys_to_use}


__all__ = ["run_autopilot"]
