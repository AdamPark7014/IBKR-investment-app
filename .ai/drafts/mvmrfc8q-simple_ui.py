from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _esc(x: Any) -> str:
    return html.escape('' if x is None else str(x), quote=True)

def _fmt_pct(x: Any) -> str:
    try:
        return f'{float(x)*100:.1f}%'
    except Exception:
        return '—'

def render_simple_console(payload: Mapping[str, Any], *, title: str = 'ibtrader') -> str:
    facts = payload.get('facts') or {}
    brief = payload.get('brief') or {}
    text = _esc(brief.get('text') or '')
    source = _esc(brief.get('source') or 'deterministic')
    as_of = _esc(facts.get('as_of') or '—')
    trend = facts.get('equity_trend')
    trend_lbl = {1:'Alcista', -1:'Bajista', 0:'Lateral'}.get(trend, '—')
    vol = _fmt_pct(facts.get('equity_vol_20'))
    breadth = _fmt_pct(facts.get('breadth_proxy'))
    drift = _esc(facts.get('paper_n_drift') if facts.get('paper_n_drift') is not None else '—')
    risk = facts.get('risk_on_proxy')
    risk_lbl = 'ON' if risk==1 else ('OFF' if risk==0 else '—')
    ts = _esc(payload.get('generated_at') or datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    return f'''<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(title)}</title>
<style>
:root {{ --bg:#0f1419; --fg:#e7ecf1; --muted:#8b9aab; --card:#1a222c; --accent:#3d9cf0; --ok:#3dd68c; --warn:#f0b429; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family: ui-sans-serif, system-ui, Segoe UI, sans-serif; background:var(--bg); color:var(--fg); }}
main {{ max-width:720px; margin:0 auto; padding:2rem 1.25rem 3rem; }}
h1 {{ font-size:1.25rem; font-weight:600; letter-spacing:0.02em; margin:0 0 0.25rem; }}
.sub {{ color:var(--muted); font-size:0.85rem; margin-bottom:1.75rem; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:1.25rem; }}
@media (max-width:520px) {{ .grid {{ grid-template-columns:1fr; }} }}
.card {{ background:var(--card); border-radius:12px; padding:1rem 1.1rem; }}
.card .k {{ color:var(--muted); font-size:0.75rem; text-transform:uppercase; letter-spacing:0.06em; }}
.card .v {{ font-size:1.6rem; font-weight:650; margin-top:0.35rem; }}
.brief {{ background:var(--card); border-radius:12px; padding:1.1rem 1.2rem; white-space:pre-wrap; line-height:1.45; font-size:0.98rem; max-width:50ch; margin:0 auto 1.5rem; }}
.meta {{ margin-top:0.85rem; color:var(--muted); font-size:0.75rem; }}
.foot {{ margin-top:1.5rem; color:var(--muted); font-size:0.75rem; }}
</style></head><body><main>
<h1>{_esc(title)}</h1>
<p class="sub">Una pantalla. El backend ya hizo el trabajo pesado. {ts}</p>
<div class="grid">
  <div class="card"><div class="k">Mercado</div><div class="v">{_esc(trend_lbl)}</div></div>
  <div class="card"><div class="k">Vol 20d</div><div class="v">{_esc(vol)}</div></div>
  <div class="card"><div class="k">Risk proxy</div><div class="v">{_esc(risk_lbl)}</div></div>
  <div class="card"><div class="k">Paper drift</div><div class="v">{drift}</div></div>
</div>
<div class="brief">{text}</div>
<div class="meta">as_of={as_of} · breadth={_esc(breadth)} · brief={source}</div>
<p class="foot">Triage paper. No es lista de compra. No promete rentabilidad. Cero órdenes LIVE desde esta pantalla.</p>
</main></body></html>'''

def write_simple_console(payload: Mapping[str, Any], path: str | Path, *, title: str = 'ibtrader') -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_simple_console(payload, title=title), encoding='utf-8')
    return str(p)

__all__ = ['render_simple_console', 'write_simple_console']