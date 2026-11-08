"""Model quality scorecard: "perfección" turned into numbers with a target each (audit 2026-11-07, §7).

"Perfect" is not measurable. These are: each metric has a target, a value computed only from files
the daily run already writes, and a status ``pass`` / ``fail`` / ``insufficient`` (too little data to
judge; never counted as a pass). ``ready_for_live`` is True only when every metric passes AND the
paper record is at least ``MIN_PAPER_SESSIONS`` long.

Inputs (all optional; a missing file means ``insufficient``, never a crash):
* ``paper_equity.jsonl``  → realized vol vs target, max drawdown, sessions run.
* ``reports/daily/*-plan.json`` → cost drag (``nav_before - nav_after`` is what trading paid).
* ``slippage_ledger.jsonl`` (``source == "ibkr"``) → real slippage in bps.
* ``alerts.jsonl`` → reconciliation breaks, missed heartbeats, data-quality blocks.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..config import AppSettings

#: Six months of daily sessions before any live capital (audit §7, P5).
MIN_PAPER_SESSIONS = 126
MIN_FILLS_FOR_SLIPPAGE = 10
MIN_POINTS_FOR_VOL = 60


def _jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _metric(name: str, value: Optional[float], target: str, ok: Optional[bool], unit: str = "",
            note: str = "") -> Dict[str, Any]:
    status = "insufficient" if ok is None else ("pass" if ok else "fail")
    v = None if value is None or (isinstance(value, float) and not math.isfinite(value)) else round(float(value), 4)
    return {"metric": name, "value": v, "unit": unit, "target": target, "status": status, "note": note}


def _pct(values: Iterable[float], q: float) -> float:
    xs = sorted(values)
    k = max(0, min(len(xs) - 1, int(math.ceil(q * len(xs))) - 1))
    return xs[k]


def build_scorecard(settings: AppSettings) -> Dict[str, Any]:
    data = Path(settings.data.data_dir)
    eq_rows = [r for r in _jsonl(data / "paper_equity.jsonl") if isinstance(r.get("equity"), (int, float))]
    equity = [float(r["equity"]) for r in eq_rows if float(r["equity"]) > 0]
    sessions = len(equity)
    alerts = _jsonl(Path(settings.ops.alerts_file))
    slips = [float(r["slip_bps"]) for r in _jsonl(data / "slippage_ledger.jsonl")
             if r.get("source") == "ibkr" and isinstance(r.get("slip_bps"), (int, float))]
    out: List[Dict[str, Any]] = []

    # 1. Operational continuity: the daily job ran every day.
    missed = sum(1 for a in alerts if a.get("code") == "heartbeat")
    out.append(_metric("heartbeats_perdidos", missed, "= 0", missed == 0 if sessions else None,
                       note="cada alerta 'heartbeat' es un día sin corrida"))

    # 2. Book vs broker: zero reconciliation breaks.
    breaks = sum(1 for a in alerts if a.get("code") == "reconcile_break")
    out.append(_metric("descuadres_con_broker", breaks, "= 0", breaks == 0 if sessions else None))

    # 3. Data quality: blocked sessions because data was stale or sources disagreed.
    dq = sum(1 for a in alerts if a.get("code") == "data_quality")
    rate = dq / sessions if sessions else None
    out.append(_metric("sesiones_con_datos_malos", rate, "<= 2 %", (rate <= 0.02) if rate is not None else None,
                       unit="fracción", note=f"{dq} alertas data_quality en {sessions} sesiones"))

    # 4. Real slippage vs the midpoint at decision (only IBKR fills count).
    if len(slips) >= MIN_FILLS_FOR_SLIPPAGE:
        med, p90 = statistics.median(slips), _pct(slips, 0.9)
        out.append(_metric("slippage_mediano", med, "<= 5 bps", med <= 5.0, unit="bps"))
        out.append(_metric("slippage_p90", p90, "<= 15 bps", p90 <= 15.0, unit="bps"))
    else:
        note = f"{len(slips)} fills reales; hacen falta {MIN_FILLS_FOR_SLIPPAGE}"
        out.append(_metric("slippage_mediano", None, "<= 5 bps", None, unit="bps", note=note))
        out.append(_metric("slippage_p90", None, "<= 15 bps", None, unit="bps", note=note))

    # 5. Cost drag: what trading paid (spread + commission), annualized, as % of NAV.
    reports = sorted(Path(settings.data.reports_dir, "daily").glob("*-plan.json"))
    paid, navs = 0.0, []
    for rp in reports:
        try:
            rep = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        nb, na = rep.get("nav_before"), rep.get("nav_after")
        if isinstance(nb, (int, float)) and isinstance(na, (int, float)) and nb > 0:
            paid += max(0.0, float(nb) - float(na))
            navs.append(float(nb))
    if len(navs) >= 20:
        drag = paid / statistics.mean(navs) * (252.0 / len(navs))
        out.append(_metric("coste_anual_de_operar", drag, "<= 0.30 % anual", drag <= 0.003, unit="fracción/año"))
    else:
        out.append(_metric("coste_anual_de_operar", None, "<= 0.30 % anual", None, unit="fracción/año",
                           note=f"{len(navs)} informes diarios; hacen falta 20"))

    # 6. Realized vol close to the target the sizing aims at.
    target_vol = float(settings.risk.target_vol_annual)
    if sessions >= MIN_POINTS_FOR_VOL:
        rets = [equity[i] / equity[i - 1] - 1.0 for i in range(1, sessions)]
        vol = statistics.pstdev(rets) * math.sqrt(252.0)
        ok = abs(vol - target_vol) <= 0.3 * target_vol
        out.append(_metric("volatilidad_realizada", vol, f"{target_vol:.0%} ± 30 %", ok, unit="anual"))
    else:
        out.append(_metric("volatilidad_realizada", None, f"{target_vol:.0%} ± 30 %", None, unit="anual",
                           note=f"{sessions} sesiones; hacen falta {MIN_POINTS_FOR_VOL}"))

    # 7. Max drawdown inside the configured limit.
    limit = float(settings.risk.drawdown_limit_pct) / 100.0
    if sessions >= 2:
        peak, mdd = equity[0], 0.0
        for e in equity:
            peak = max(peak, e)
            mdd = min(mdd, e / peak - 1.0)
        out.append(_metric("caida_maxima", mdd, f">= -{limit:.0%}", mdd >= -limit, unit="fracción"))
    else:
        out.append(_metric("caida_maxima", None, f">= -{limit:.0%}", None, unit="fracción"))

    # 8. Track record length.
    out.append(_metric("sesiones_en_paper", sessions, f">= {MIN_PAPER_SESSIONS}", sessions >= MIN_PAPER_SESSIONS,
                       note="seis meses de paper antes de dinero real"))

    statuses = [m["status"] for m in out]
    return {
        "metrics": out,
        "n_pass": statuses.count("pass"),
        "n_fail": statuses.count("fail"),
        "n_insufficient": statuses.count("insufficient"),
        "ready_for_live": all(s == "pass" for s in statuses),
        "note": "La rentabilidad no es una meta del scorecard: se mide, pero solo cuenta después de pasar "
                "la compuerta de investigación (DSR >= 0.95, t >= 3, >= 252 observaciones).",
    }


__all__ = ["MIN_PAPER_SESSIONS", "build_scorecard"]
