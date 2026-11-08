"""Claude como copiloto del modelo: opina, explica e investiga, pero nunca envía órdenes.

Tres funciones, todas por la puerta (``triage._call``) y todas medibles:

1. **Opinión diaria en sombra** (``daily_opinion``). Después del plan, Claude recibe los hechos del día
   (objetivos, pesos actuales, retornos recientes, caída, alertas) y devuelve por ETF ``aumentar`` /
   ``mantener`` / ``reducir`` con convicción 1-3, más un resumen en español de por qué el sistema hace lo
   que hace. Se guarda con fecha en ``data/copilot_opinions.jsonl`` junto con los precios de cierre del día.
   El plan y las órdenes no cambian.
2. **Medición** (``score_opinions``). Cada opinión define una cartera sombra = pesos del sistema inclinados
   según Claude (``copilot_tilt``). Entre una opinión y la siguiente se compara su retorno con el del
   sistema solo, usando solo precios posteriores a la opinión (sin mirar al futuro). Va al scorecard como
   dato informativo: ``ready_for_live`` no depende de él. Hacen falta ``MIN_SESSIONS_TO_JUDGE`` sesiones y
   t >= 3 antes de pensar en darle peso real.
3. **Investigación propia** (``propose_hypotheses``). Claude propone configuraciones nuevas usando solo
   reglas y ponderaciones que ya existen en el pipeline. ``research-portfolio --hypotheses`` las corre
   por la misma compuerta y cada una cuenta como una prueba más en el DSR.

Por qué no decide órdenes: un modelo de lenguaje ya "vio" el pasado en su entrenamiento, así que cualquier
backtest de sus decisiones históricas está contaminado. La única prueba limpia es hacia adelante, en sombra.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional

from pydantic import BaseModel, ValidationError

from .triage import _call, _schema

COPILOT_MODEL = "claude-haiku-5-5"
#: Inclinación máxima por ETF con convicción 3 (±20 % de su peso), renormalizada al bruto del sistema.
MAX_TILT = 0.20
#: Seis meses de sesiones antes de juzgar si Claude aporta (igual que el paper antes de dinero real).
MIN_SESSIONS_TO_JUDGE = 126
WEIGHTINGS = ("box_risk_parity", "hrp", "equal")


class SymbolView(BaseModel):
    symbol: str
    stance: Literal["aumentar", "mantener", "reducir"]
    conviction: Literal[1, 2, 3]
    reason: str


class Opinion(BaseModel):
    summary: str
    risks: List[str]
    views: List[SymbolView]


class RuleWeight(BaseModel):
    rule: str
    weight: float


class Proposal(BaseModel):
    name: str
    rules: List[RuleWeight]
    weighting: Literal["box_risk_parity", "hrp", "equal"]
    rationale: str


class Proposals(BaseModel):
    hypotheses: List[Proposal]


class Hypothesis(BaseModel):
    """Hipótesis ya validada: reglas existentes y pesos que suman 1."""

    name: str
    rules: List[str]
    rule_weights: Dict[str, float]
    weighting: Literal["box_risk_parity", "hrp", "equal"]
    rationale: str


OPINION_SYSTEM = (
    "Eres el copiloto de ibtrader, un sistema de tendencia y paridad de riesgo con ETF que rebalancea una vez "
    "al día en Interactive Brokers. Recibes HECHOS en JSON con los datos hasta el cierre de hoy: pesos objetivo "
    "del sistema, pesos actuales, retornos de 1, 5, 21 y 63 sesiones por ETF, caída actual y alertas. "
    "Tu opinión NO cambia las órdenes: se registra y se mide contra el sistema durante meses. "
    "Responde solo con el JSON pedido, en español. summary: 3-5 frases claras para una persona no experta "
    "que expliquen qué hace hoy el sistema y por qué. risks: hasta 3 riesgos concretos de la cartera de hoy. "
    "views: un elemento por cada ETF de los hechos; 'mantener' con convicción 1 cuando no tengas una razón "
    "fundada en los hechos. No inventes noticias ni datos que no estén en los hechos; si dudas, 'mantener'."
)

RESEARCH_SYSTEM = (
    "Eres el investigador de ibtrader (tendencia + paridad de riesgo con ETF, solo largos, sin apalancamiento). "
    "Recibes en JSON los resultados de la última investigación con datos reales y las reglas y ponderaciones "
    "disponibles. Propón como máximo 3 configuraciones nuevas que puedan mejorar el Sharpe neto fuera de "
    "muestra, usando SOLO nombres de reglas y ponderaciones de la lista. Cada propuesta cuenta como una prueba "
    "más y endurece la compuerta para todas, así que propón solo lo que tenga una razón económica clara, "
    "no variaciones para exprimir el pasado. rules: lista de {rule, weight} con pesos que sumen 1. rationale: en "
    "español, 2-3 frases, citando la evidencia de los resultados."
)


def _ret(closes: List[float], n: int) -> Optional[float]:
    if len(closes) <= n or closes[-1 - n] <= 0:
        return None
    return round(closes[-1] / closes[-1 - n] - 1.0, 4)


def build_facts(
    as_of: str,
    targets: Mapping[str, float],
    current: Mapping[str, float],
    closes: Mapping[str, List[float]],
    drawdown: Optional[float],
    alerts: Iterable[str] = (),
) -> Dict[str, Any]:
    """Hechos del día para la opinión. Solo datos hasta el cierre de ``as_of``."""
    rows = {}
    for sym in sorted(set(targets) | set(current)):
        c = list(closes.get(sym) or [])
        rows[sym] = {
            "peso_objetivo": round(float(targets.get(sym, 0.0)), 4),
            "peso_actual": round(float(current.get(sym, 0.0)), 4),
            "ret_1d": _ret(c, 1), "ret_5d": _ret(c, 5), "ret_21d": _ret(c, 21), "ret_63d": _ret(c, 63),
        }
    return {"fecha": as_of, "etf": rows, "caida_actual": drawdown, "alertas": list(alerts)}


def daily_opinion(
    facts: Mapping[str, Any],
    *,
    data_dir: str | Path = "./data",
    budget_usd: float = 10.0,
    model: str = COPILOT_MODEL,
    client: Any = None,
) -> Optional[Opinion]:
    text = _call(
        proceso="ibtrader-copiloto", model=model, system=OPINION_SYSTEM,
        payload=json.dumps(dict(facts), sort_keys=True, ensure_ascii=False, default=str),
        schema=_schema(Opinion), effort="medium", max_tokens=4000, data_dir=data_dir, budget_usd=budget_usd,
        client=client,
    )
    if not text:
        return None
    try:
        op = Opinion.model_validate_json(text)
    except ValidationError:
        return None
    known = set((facts.get("etf") or {}).keys())
    op.views = [v for v in op.views if v.symbol in known]
    return op


def copilot_tilt(weights: Mapping[str, float], views: Iterable[SymbolView | Mapping[str, Any]],
                 max_tilt: float = MAX_TILT) -> Dict[str, float]:
    """Pesos del sistema inclinados por las opiniones, con el mismo bruto (no añade apalancamiento)."""
    w = {s: float(x) for s, x in weights.items()}
    gross = sum(abs(x) for x in w.values())
    out = dict(w)
    for v in views:
        d = v.model_dump() if isinstance(v, BaseModel) else dict(v)
        sym = str(d.get("symbol"))
        if sym not in out or d.get("stance") == "mantener":
            continue
        k = max_tilt * int(d.get("conviction") or 1) / 3.0
        out[sym] = out[sym] * (1.0 + k if d.get("stance") == "aumentar" else 1.0 - k)
    new_gross = sum(abs(x) for x in out.values())
    if new_gross > 0 and gross > 0:
        out = {s: x * gross / new_gross for s, x in out.items()}
    return out


def record_opinion(path: str | Path, as_of: str, weights: Mapping[str, float], closes: Mapping[str, float],
                   opinion: Opinion, model: str = COPILOT_MODEL) -> Dict[str, Any]:
    row = {
        "fecha": as_of, "model": model,
        "weights": {s: round(float(x), 6) for s, x in weights.items()},
        "closes": {s: float(x) for s, x in closes.items()},
        "tilted": {s: round(x, 6) for s, x in copilot_tilt(weights, opinion.views).items()},
        **opinion.model_dump(),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return row


def _load(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and r.get("fecha"):
            rows.append(r)
    by_date = {str(r["fecha"]): r for r in rows}  # una opinión por sesión: gana la última
    return [by_date[k] for k in sorted(by_date)]


def score_opinions(path: str | Path) -> Dict[str, Any]:
    """Valor añadido de la inclinación de Claude frente al sistema, sesión a sesión, sin mirar al futuro."""
    rows = _load(path)
    diffs: List[float] = []
    for prev, nxt in zip(rows, rows[1:]):
        c0, c1 = prev.get("closes") or {}, nxt.get("closes") or {}

        def port(w: Mapping[str, float]) -> Optional[float]:
            tot = 0.0
            for s, x in w.items():
                if float(x) == 0.0:
                    continue
                if not (c0.get(s) and c1.get(s)):
                    return None
                tot += float(x) * (float(c1[s]) / float(c0[s]) - 1.0)
            return tot

        rs, rt = port(prev.get("weights") or {}), port(prev.get("tilted") or {})
        if rs is not None and rt is not None:
            diffs.append(rt - rs)
    n = len(diffs)
    out: Dict[str, Any] = {"opiniones": len(rows), "sesiones_medidas": n, "minimo_para_juzgar": MIN_SESSIONS_TO_JUDGE}
    if n >= 2:
        mean, sd = statistics.mean(diffs), statistics.pstdev(diffs)
        out.update({
            "exceso_total": round(sum(diffs), 6),
            "exceso_anual": round(mean * 252.0, 6),
            "acierto": round(sum(1 for d in diffs if d > 0) / n, 4),
            "t": round(mean / sd * math.sqrt(n), 3) if sd > 0 else None,
        })
    t = out.get("t")
    if n < MIN_SESSIONS_TO_JUDGE:
        out["estado"] = "insuficiente"
    else:
        out["estado"] = "aporta" if (t is not None and t >= 3.0) else "no_demostrado"
    return out


def propose_hypotheses(
    context: Mapping[str, Any],
    available_rules: Iterable[str],
    *,
    data_dir: str | Path = "./data",
    budget_usd: float = 10.0,
    model: str = COPILOT_MODEL,
    client: Any = None,
) -> List[Hypothesis]:
    """Hipótesis de Claude filtradas a reglas y ponderaciones que existen; pesos renormalizados a 1."""
    rules = sorted(set(available_rules))
    payload = {"resultados": dict(context), "reglas_disponibles": rules, "ponderaciones": list(WEIGHTINGS)}
    text = _call(
        proceso="ibtrader-investigacion", model=model, system=RESEARCH_SYSTEM,
        payload=json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
        schema=_schema(Proposals), effort="high", max_tokens=8000, data_dir=data_dir, budget_usd=budget_usd,
        client=client,
    )
    if not text:
        return []
    try:
        hyps = Proposals.model_validate_json(text).hypotheses
    except ValidationError:
        return []
    valid: List[Hypothesis] = []
    allowed = set(rules)
    for h in hyps[:3]:
        ws: Dict[str, float] = {}
        for rw in h.rules:
            if rw.rule in allowed:
                ws[rw.rule] = ws.get(rw.rule, 0.0) + max(0.0, float(rw.weight))
        rs = list(ws)
        if not rs:
            continue
        tot = sum(ws.values())
        ws = {r: x / tot for r, x in ws.items()} if tot > 0 else {r: 1.0 / len(rs) for r in rs}
        slug = "".join(ch if ch.isalnum() else "_" for ch in h.name.lower())[:40].strip("_") or "hipotesis"
        valid.append(Hypothesis(name=f"copiloto_{slug}", rules=rs, rule_weights=ws, weighting=h.weighting,
                                rationale=h.rationale))
    return valid


def load_hypotheses(path: str | Path) -> List[Hypothesis]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("hypotheses", raw) if isinstance(raw, dict) else raw
    return [Hypothesis.model_validate(h) for h in items]


__all__ = [
    "COPILOT_MODEL", "Hypothesis", "MIN_SESSIONS_TO_JUDGE", "Opinion", "SymbolView", "build_facts",
    "copilot_tilt", "daily_opinion", "load_hypotheses", "propose_hypotheses", "record_opinion", "score_opinions",
]
