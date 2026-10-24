from __future__ import annotations
import json, os
from typing import Any, Dict, Mapping, Optional
from .prompt_pack import PromptPack, default_pack

def compress_facts(*, radar: Mapping[str, Any] | None = None, paper: Mapping[str, Any] | None = None, posture: Mapping[str, Any] | None = None, slippage: Mapping[str, Any] | None = None, extra: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    '''JSON pequeño para IA / UI. Sin series crudas.'''
    r = dict(radar or {})
    p = dict(paper or {})
    facts: Dict[str, Any] = {
        'as_of': r.get('as_of'),
        'equity_trend': r.get('equity_trend'),
        'equity_vol_20': _round(r.get('equity_vol_20'), 4),
        'risk_on_proxy': r.get('risk_on_proxy'),
        'breadth_proxy': _round(r.get('breadth_proxy'), 3),
        'rates_slope': _round(r.get('rates_slope'), 4),
        'commodity_momentum': _round(r.get('commodity_momentum'), 4),
        'paper_n_drift': p.get('n_drift'),
        'paper_n_symbols': p.get('n_symbols'),
        'orders_sent': p.get('orders_sent', 0),
        'posture': posture or {},
        'slippage_n': (slippage or {}).get('n'),
        'slippage_mean_bps': _round((slippage or {}).get('mean_slip_bps'), 2),
        'disclaimer': r.get('disclaimer') or 'Triage only. Not predictive of returns.',
    }
    if extra:
        facts['extra'] = dict(extra)
    return facts

def _round(v: Any, n: int) -> Any:
    try:
        return None if v is None else round(float(v), n)
    except (TypeError, ValueError):
        return None

def _trend_label(t: Any) -> str:
    if t == 1: return 'alcista vs MA100'
    if t == -1: return 'bajista vs MA100'
    if t == 0: return 'lateral vs MA100'
    return 'sin señal de tendencia'

def deterministic_brief(facts: Mapping[str, Any]) -> str:
    '''Narrativa intuitiva sin llamar a ningún LLM.'''
    lines = []
    lines.append(f\"Estado ({facts.get('as_of') or 'n/d'}): mercado {_trend_label(facts.get('equity_trend'))}.\")
    bullets = []
    if facts.get('equity_vol_20') is not None:
        bullets.append(f\"Vol 20d anualizada ≈ {float(facts['equity_vol_20'])*100:.1f}%.\")
    if facts.get('risk_on_proxy') is not None:
        bullets.append('VIX bajo su MA50 (risk-on proxy).' if facts['risk_on_proxy']==1 else 'VIX alto vs MA50 (risk-off proxy).')
    if facts.get('breadth_proxy') is not None:
        bullets.append(f\"Breadth: {float(facts['breadth_proxy'])*100:.0f}% de símbolos > MA50.\")
    if facts.get('paper_n_drift') is not None:
        bullets.append(f\"Paper: {facts['paper_n_drift']} símbolos con drift desired≠held; órdenes enviadas={facts.get('orders_sent',0)}.\")
    if facts.get('slippage_n'):
        bullets.append(f\"Slippage ledger: n={facts['slippage_n']}, mean≈{facts.get('slippage_mean_bps')} bps.\")
    for b in bullets[:5]:
        lines.append(f\"- {b}\")
    drift = int(facts.get('paper_n_drift') or 0)
    if drift > 0:
        lines.append('Acción paper: revisar paper-reconcile; no LIVE. ESPERAR órdenes reales.')
    else:
        lines.append('Acción paper: sin drift material — ESPERAR / observar.')
    lines.append(str(facts.get('disclaimer') or ''))
    return '\n'.join(lines)

def ai_brief(facts: Mapping[str, Any], *, pack: Optional[PromptPack] = None, use_ai: bool = True) -> Dict[str, Any]:
    '''Devuelve {text, source, model, pack}. source=deterministic|ai|ai_fallback.'''
    pack = pack or default_pack()
    det = deterministic_brief(facts)
    out: Dict[str, Any] = {'text': det, 'source': 'deterministic', 'model': None, 'pack': pack.name, 'facts': dict(facts)}
    if not use_ai:
        return out
    if not os.environ.get('ANTHROPIC_API_KEY'):
        out['source'] = 'deterministic'
        out['note'] = 'no ANTHROPIC_API_KEY'
        return out
    try:
        import anthropic
    except ImportError:
        out['note'] = 'anthropic SDK not installed (pip install anthropic)'
        return out
    try:
        client = anthropic.Anthropic()
        kwargs: Dict[str, Any] = dict(
            model=pack.model,
            max_tokens=int(pack.max_tokens),
            temperature=float(pack.temperature),
            system=[{'type':'text','text': pack.render_system(), 'cache_control': {'type':'ephemeral'}}],
            messages=[{'role':'user','content': pack.render_user(facts)}],
            extra_headers={'x-proceso': pack.proceso},
        )
        # effort si el SDK lo soporta
        try:
            kwargs['output_config'] = {'effort': pack.effort}
        except Exception:
            pass
        r = client.messages.create(**kwargs)
        text = ''.join(b.text for b in r.content if getattr(b, 'type', None)=='text')
        if text.strip():
            out['text'] = text.strip()
            out['source'] = 'ai'
            out['model'] = pack.model
        else:
            out['source'] = 'ai_fallback'
            out['note'] = 'empty model response'
    except Exception as exc:  # noqa: BLE001 — fall closed to deterministic
        out['source'] = 'ai_fallback'
        out['note'] = f'{type(exc).__name__}: {exc}'
    return out

__all__ = ['compress_facts', 'deterministic_brief', 'ai_brief']