from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import AppSettings
from ..data.service import load_universe_v2
from ..engine.decision import DecisionEngine
from ..execution.passive_aggressive import decide_urgency
from ..intelligence.brief import ai_brief, compress_facts
from ..intelligence.market_radar import build_market_radar
from ..intelligence.prompt_pack import PromptPack, default_pack
from .alerts import Alert, evaluate_paper_alerts
from .config_freeze import verify_freeze, write_freeze
from .paper_curve import append_equity_point, estimate_mark_to_market, paper_max_drawdown, load_equity_points
from .paper_stack import PaperStack
from .paper_vs_oos import compare_paper_vs_oos
from .shadow import desired_from_decisions, log_shadow_snapshot
from .simple_ui import write_simple_console
from .urgency_age import load_open_order_age_seconds


def _load_held(path: Path) -> Dict[str, float]:
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
    data = load_universe_v2(s)
    radar = build_market_radar(data)

    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    desired = desired_from_decisions(decisions)
    held_path = Path(s.data.data_dir) / "paper_positions.json"
    held = _load_held(held_path)
    paper = log_shadow_snapshot(desired, held, tag="autopilot")
    paper["orders_sent"] = 0
    stack = PaperStack(Path(s.data.data_dir) / 'paper_stack.sqlite')
    stack.sync_from_json(desired, held)
    stack_snap = stack.snapshot()
    paper_stack_info = {'n_drift': sum(1 for row in stack_snap.get('drift', []) if float(row.get('delta', 0)) != 0.0)}
    paper["shadow_held_source"] = str(held_path) if held_path.exists() else None

    # --- Cableado freeze + urgency: ANTES de compress_facts ---
    freeze_path = Path(s.data.data_dir) / 'paper_config_freeze.json'
    if not freeze_path.is_file():
        write_freeze(freeze_path, s)
    freeze = verify_freeze(freeze_path, s)

    open_orders_path = Path(s.data.data_dir) / 'paper_open_orders.json'
    age_seconds = load_open_order_age_seconds(open_orders_path)
    urgency = decide_urgency(age_seconds=age_seconds, max_passive_seconds=60.0, touchable=True)
    # ------------------------------------

    slip = _slippage_summary(Path(s.data.data_dir))

    facts = compress_facts(
        radar=radar, 
        paper=paper, 
        slippage=slip,
        extra={
            'urgency_mode': urgency.mode, 
            'urgency_reason': urgency.reason, 
            'config_hash_ok': freeze.get('ok'), 
            'config_hash': freeze.get('actual') or freeze.get('expected')
        }
    )

    brief = ai_brief(facts, pack=pack or default_pack(), use_ai=use_ai)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(s.data.reports_dir) / "autopilot"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_drift_val = int(paper_stack_info.get('n_drift') or 0)
    paper_equity_path = Path(s.data.data_dir) / "paper_equity.jsonl"
    
    last_prices: Dict[str, float] = {}
    for sym, df in (data or {}).items():
        try:
            if df is None or len(df) == 0:
                continue
            col = "close" if hasattr(df, "columns") and "close" in df.columns else (df.columns[0] if hasattr(df, "columns") and len(df.columns) else None)
            if col is None:
                continue
            last_prices[str(sym)] = float(df[col].iloc[-1])
        except Exception:
            continue
    
    mtm = estimate_mark_to_market(held, last_prices)
    if mtm is not None:
        append_equity_point(paper_equity_path, mtm)

    max_dd = paper_max_drawdown(paper_equity_path) if paper_equity_path.is_file() else None
    load_n_points = len(load_equity_points(paper_equity_path)) if paper_equity_path.is_file() else 0
    paper_vs_oos = compare_paper_vs_oos(
        paper_max_dd=max_dd,
        paper_n_points=load_n_points,
        assumed_sharpe=0.8,
    )
    
    alerts = evaluate_paper_alerts(
        max_drawdown=max_dd,
        assumed_sharpe=0.8,
        n_drift=n_drift_val,
        orders_sent=0,
    )
    if not freeze.get("ok"):
        alerts.append(
            Alert(
                code="config_drift",
                severity="kill_recommend",
                message="paper config hash mismatch — do not retune live",
            )
        )

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
        # Payload añade 'config_freeze' y urgencia según instrucción
        "config_freeze": freeze,
        "urgency": {'mode': urgency.mode, 'reason': urgency.reason},
        "paper_stack": paper_stack_info,
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
    base_keys = ("text", "source