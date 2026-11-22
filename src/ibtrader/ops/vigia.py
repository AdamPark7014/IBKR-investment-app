"""Vigía: decide qué le toca a la corrida diaria y lo recupera si se perdió su hora.

Las tareas de hora fija (plan 19:00 y ejecución 10:05 de Nueva York) se pierden cuando la laptop está
apagada o dormida a esa hora exacta: en las primeras 9 sesiones de paper solo hubo 2 ejecuciones. El
vigía corre cada 15 minutos y en cada vuelta pregunta qué falta:

* **plan**: no hay informe de plan de la última sesión cerrada y ya pasaron ``PLAN_AFTER_CLOSE`` desde
  el cierre (el proveedor de datos ya publicó). Si el plan anterior falló por datos, reintenta cada
  ``PLAN_RETRY``.
* **execute**: hay órdenes pendientes de esa sesión, el mercado está abierto, ya pasó la espera tras la
  apertura y falta más de ``EXECUTE_CUTOFF`` para el cierre. Con el Gateway cerrado no intenta nada y
  avisa **una vez** por sesión.
* **nada**: en cualquier otro caso.

No decide nada de inversión: solo cuándo llamar a ``run_plan`` y ``run_execute``, que conservan todos sus
controles (freeze, conciliación, pre-trade, órdenes idempotentes, pendientes caducadas). Un candado
evita dos corridas a la vez.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from ..config import AppSettings
from ..data.crosscheck import last_completed_session
from ..execution.session import ET, is_rth, is_trading_day, session_close
from .notify import emit_alert
from .run_daily import Paths

#: Espera desde el cierre antes de planear: Tiingo publica el cierre entre 17:30 y 18:00 de Nueva York.
PLAN_AFTER_CLOSE = timedelta(hours=3)
#: Reintento del plan cuando el anterior quedó sin datos válidos.
PLAN_RETRY = timedelta(minutes=60)
#: No empezar a ejecutar tan cerca del cierre: las órdenes pasivas necesitan tiempo para llenarse.
EXECUTE_CUTOFF = timedelta(minutes=45)
#: Intentos de ejecución por sesión (el Gateway abre el puerto pero no responde, sesión sin 2FA...).
MAX_EXECUTE_ATTEMPTS = 4
#: Una corrida más vieja que esto se da por muerta y su candado se ignora.
LOCK_MAX_AGE = timedelta(minutes=30)
#: Desde cuánto antes de la apertura se avisa de que el Gateway está cerrado.
GATEWAY_WARN_BEFORE_OPEN = timedelta(minutes=45)


@dataclass(frozen=True)
class Decision:
    action: str  # "plan" | "execute" | "nada"
    reason: str
    session: str
    alert: Optional[str] = None  # código de aviso a emitir una sola vez por sesión

    def to_dict(self) -> Dict[str, Any]:
        return {"accion": self.action, "motivo": self.reason, "sesion": self.session, "aviso": self.alert}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _aware(ts: Any) -> Optional[datetime]:
    try:
        out = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return out if out.tzinfo is not None else out.replace(tzinfo=timezone.utc)


def _open_et(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)


def _close_et(day: date) -> datetime:
    return datetime.combine(day, session_close(day), tzinfo=ET)


def state_path(settings: AppSettings) -> Path:
    return Path(settings.data.data_dir) / "vigia_state.json"


def lock_path(settings: AppSettings) -> Path:
    return Path(settings.data.data_dir) / "vigia.lock"


def decide(
    settings: AppSettings,
    now: datetime,
    *,
    port_open: Callable[[], bool],
    state: Optional[Mapping[str, Any]] = None,
) -> Decision:
    """Qué toca ahora. Función pura salvo por leer los informes y las órdenes pendientes."""
    paths = Paths.from_settings(settings)
    state = dict(state or {})
    session = last_completed_session(now)
    sid = session.isoformat()

    # 1. ¿Falta el plan de la última sesión cerrada?
    plan = _read_json(paths.reports / f"{sid}-plan.json")
    if now >= _close_et(session) + PLAN_AFTER_CLOSE:
        if not plan:
            return Decision("plan", "no hay plan de la última sesión cerrada", sid)
        failed = plan.get("status") == "data_error" or (plan.get("freshness") or {}).get("ok") is False
        started = _aware(plan.get("started_at"))
        if failed and (started is None or now - started >= PLAN_RETRY):
            return Decision("plan", "el plan anterior quedó sin datos válidos: reintento", sid)

    # 2. ¿Hay órdenes de esa sesión esperando la apertura?
    if settings.execution.mode == "shadow" or not paths.pending.is_file():
        return Decision("nada", "sin órdenes pendientes", sid)
    pending = _read_json(paths.pending)
    if str(pending.get("run_date")) != sid:
        # run_execute las marca como caducadas; solo vale la pena llamarlo con el mercado abierto.
        return (Decision("execute", "órdenes pendientes de otra sesión: se archivan como caducadas", sid)
                if is_rth(now) else Decision("nada", "órdenes pendientes de otra sesión; mercado cerrado", sid))
    today = now.astimezone(ET).date()
    if not is_trading_day(today):
        return Decision("nada", "hoy no hay sesión", sid)
    open_et, close_et = _open_et(today), _close_et(today)
    ready_at = open_et + timedelta(minutes=settings.execution.min_minutes_after_open)
    if now < open_et - GATEWAY_WARN_BEFORE_OPEN:
        return Decision("nada", "falta para la apertura", sid)
    if now >= close_et - EXECUTE_CUTOFF:
        missed = now < close_et + timedelta(hours=2)
        return Decision("nada", "ya no da tiempo de ejecutar hoy", sid, alert="sesion_perdida" if missed else None)
    if not port_open():
        return Decision("nada", "el Gateway de IBKR no está abierto", sid, alert="gateway_cerrado")
    if now < ready_at:
        return Decision("nada", "espera tras la apertura", sid)
    attempts = int((state.get("execute_attempts") or {}).get(sid, 0))
    if attempts >= MAX_EXECUTE_ATTEMPTS:
        return Decision("nada", f"{attempts} intentos de ejecución sin éxito: requiere revisión", sid,
                        alert="ejecucion_agotada")
    return Decision("execute", "órdenes pendientes y mercado abierto", sid)


_ALERTS: Dict[str, tuple] = {
    "gateway_cerrado": ("critical", "hay órdenes pendientes y el Gateway de IBKR no está abierto: ábrelo (puerto de "
                                    "paper) para que se ejecuten hoy"),
    "sesion_perdida": ("warn", "las órdenes de hoy no se ejecutaron antes del cierre; el próximo plan las recalcula"),
    "ejecucion_agotada": ("critical", "la ejecución falló varias veces hoy: revisa el Gateway y data/alerts.jsonl"),
}


def acquire_lock(settings: AppSettings, now: datetime) -> bool:
    """Candado de archivo: ``False`` si otra corrida empezó hace menos de ``LOCK_MAX_AGE``."""
    p = lock_path(settings)
    started = _aware(_read_json(p).get("ts"))
    if started is not None and now - started < LOCK_MAX_AGE:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ts": now.isoformat()}), encoding="utf-8")
    return True


def release_lock(settings: AppSettings) -> None:
    lock_path(settings).unlink(missing_ok=True)


def _save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(state), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def tick(
    settings: AppSettings,
    *,
    run_phase: Callable[[str], Mapping[str, Any]],
    port_open: Callable[[], bool],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Una vuelta del vigía: decide, avisa una vez por sesión y, si toca, corre la fase."""
    now = now or datetime.now(timezone.utc)
    sp = state_path(settings)
    state = _read_json(sp)
    if not acquire_lock(settings, now):
        return {"accion": "nada", "motivo": "otra corrida en curso", "ts": now.isoformat()}
    try:
        d = decide(settings, now, port_open=port_open, state=state)
        out: Dict[str, Any] = {**d.to_dict(), "ts": now.isoformat()}
        if d.alert:
            sent = dict(state.get("alerts") or {})
            if sent.get(d.alert) != d.session:
                sev, msg = _ALERTS[d.alert]
                emit_alert(settings.ops, d.alert, sev, msg, {"sesion": d.session}, now=now)
                sent[d.alert] = d.session
                state["alerts"] = sent
        if d.action in ("plan", "execute"):
            if d.action == "execute":
                tries = {d.session: int((state.get("execute_attempts") or {}).get(d.session, 0)) + 1}
                state["execute_attempts"] = tries  # solo la sesión en curso: el archivo no crece
            _save_state(sp, state)  # antes de correr: un intento que muere a medias también cuenta
            rep = run_phase(d.action)
            out["estado"] = rep.get("status")
            out["ordenes_enviadas"] = rep.get("orders_sent")
        state["ultima_vuelta"] = out
        _save_state(sp, state)
        return out
    finally:
        release_lock(settings)


__all__ = [
    "Decision", "EXECUTE_CUTOFF", "MAX_EXECUTE_ATTEMPTS", "PLAN_AFTER_CLOSE", "PLAN_RETRY",
    "acquire_lock", "decide", "lock_path", "release_lock", "state_path", "tick",
]
