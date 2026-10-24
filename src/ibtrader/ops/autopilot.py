from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import AppSettings
from ..data.service import load_universe_v2
from ..engine.decision import DecisionEngine
from ..intelligence.brief import ai_brief, compress_facts
from ..intelligence.market_radar import build_market_radar
from ..intelligence.prompt_pack import PromptPack, default_pack
from .shadow import desired_from_decisions, log_shadow_snapshot
from .simple_ui import write_simple_console


def _load_held(path: Path) -> Dict[str, float]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    return {}

def _slippage_summary(data_dir: Path, window_days: int = 30) -> Optional[Dict[str, Any]]:
    ledger = data_dir / 'slippage_ledger.jsonl'
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
    '''Pipeline: data → radar → paper shadow → brief → HTML. No broker orders.'''
    s = settings or AppSettings()
    s.resolve_paths()
    data = load_universe_v2(s)
    radar = build_market_radar(data)

    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    desired = desired_from_decisions(decisions)
    held_path = Path(s.data.data_dir) / 'paper_positions.json'
    held = _load_held(held_path)
    paper = log_shadow_snapshot(desired, held, tag='autopilot')
    paper['orders_sent'] = 0
    paper['shadow_held_source'] = str(held_path) if held_path.exists() else None

    slip = _slippage_summary(Path(s.data.data_dir))
    facts = compress_facts(radar=radar, paper=paper, slippage=slip)
    brief = ai_brief(facts, pack=pack or default_pack(), use_ai=use_ai)

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_dir = Path(s.data.reports_dir) / 'autopilot'
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        'exp_id': run_id,
        'phase': 'autopilot-v1',
        'generated_at': run_id,
        'facts': facts,
        'brief': _build_brief_dict(brief),
        'radar': radar,
        'paper': paper,
        'orders_sent': 0,
        'disclaimer': facts.get('disclaimer'),
    }

    json_path = out_dir / f'autopilot_{run_id}.json'
    html_path = out_dir / f'autopilot_{run_id}.html'
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    write_simple_console(payload, html_path, title='ibtrader')
    # latest pointers
    (out_dir / 'latest.json').write_text(json_path.read_text(encoding='utf-8'), encoding='utf-8')
    write_simple_console(payload, out_dir / 'latest.html', title='ibtrader')

    payload['artifact_json'] = str(json_path)
    payload['artifact_html'] = str(html_path)
    payload['latest_html'] = str(out_dir / 'latest.html')

    if open_ui:
        import webbrowser
        webbrowser.open(Path(html_path).resolve().as_uri())

    return payload


def _build_brief_dict(brief: Dict[str, Any]) -> Dict[str, Any]:
    base_keys = ('text', 'source', 'model', 'pack')
    keys_to_use = [k for k in base_keys if k in brief]
    note_key = 'note'
    if note_key in brief and 'note' not in keys_to_use:
        keys_to_use.append(note_key)
    return {k: brief[k] for k in keys_to_use}


__all__ = ['run_autopilot']