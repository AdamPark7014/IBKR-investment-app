"""Chequeo previo: todo lo que tiene que estar bien antes de dejar correr el sistema, en un solo paso.

Cada comprobación devuelve ``ok`` (True, False o None = no aplica/no se pudo comprobar), un detalle y
cómo arreglarlo, en español. ``listo_sombra`` dice si la corrida diaria en sombra puede funcionar;
``listo_paper`` si ya se puede pasar a órdenes paper con IBKR (Gateway en 4002, freeze vigente; en modo
sombra, el permiso de órdenes es justo el cambio que falta hacer en .env). Nunca envía órdenes ni escribe nada.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import AppSettings

DEFAULT_PUERTA_TOKEN_FILE = r"C:\dev\secrets\puerta-ia\ibkr.token"
TASKS = ("ibtrader-run-daily-plan", "ibtrader-run-daily-execute", "ibtrader-heartbeat-check")


def _check(cid: str, ok: Optional[bool], detalle: str, arreglo: str = "", sombra: bool = True,
           paper: bool = True) -> Dict[str, Any]:
    return {"id": cid, "ok": ok, "detalle": detalle, "arreglo": "" if ok else arreglo,
            "necesario_sombra": sombra, "necesario_paper": paper}


def _mask(acct: str) -> str:
    """Número de cuenta enmascarado (DU...23) para poder pegar la salida en un chat o log."""
    return f"{acct[:2]}...{acct[-2:]}" if len(acct) > 4 else ("?" if not acct else "...")


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _tasks_registered() -> Optional[List[str]]:
    """Tareas de Windows que faltan; None fuera de Windows (no se puede comprobar)."""
    if os.name != "nt":
        return None
    missing = []
    for t in TASKS:
        r = subprocess.run(["schtasks", "/Query", "/TN", t], capture_output=True, text=True)
        if r.returncode != 0:
            missing.append(t)
    return missing


def run_preflight(
    settings: AppSettings,
    *,
    online: bool = True,
    port_open: Callable[[str, int], bool] = _port_open,
    tasks_missing: Callable[[], Optional[List[str]]] = _tasks_registered,
    tiingo_probe: Optional[Callable[[str], str]] = None,
    account_probe: Optional[Callable[[AppSettings], Tuple[Dict[str, int], Optional[float], str]]] = None,
    orders_probe: Optional[Callable[[AppSettings], Optional[str]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    from ..execution.order_manager import execution_permission
    from ..intelligence.brief import puerta_config_error
    from .config_freeze import verify_freeze

    now = now or datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    data = Path(settings.data.data_dir)

    # 1. Datos: Tiingo es la fuente principal.
    token = (settings.data.tiingo_token or "").strip()
    providers = [p.lower() for p in settings.data.providers]
    out.append(_check("tiingo_token", bool(token) and "tiingo" in providers,
                      "token de Tiingo presente" if token else "sin token de Tiingo",
                      "pon DATA__TIINGO_TOKEN=... en .env (token gratis en tiingo.com)"))
    if online and token:
        try:
            probe = tiingo_probe or _tiingo_last_date
            last = probe(token)
            out.append(_check("tiingo_responde", True, f"Tiingo responde; última barra de SPY {last}"))
        except Exception as exc:  # noqa: BLE001 - se informa, no se lanza
            out.append(_check("tiingo_responde", False, f"Tiingo no responde: {type(exc).__name__}: {exc}",
                              "revisa el token, la conexión y el límite gratis (50 consultas/hora)"))
    else:
        out.append(_check("tiingo_responde", None, "no comprobado (sin red o sin token)"))

    # 2. Estrategia y universo.
    uni = settings.data.universe_file
    uni_ok = bool(uni) and Path(str(uni)).is_file()
    out.append(_check("universo", uni_ok, f"universo: {uni or 'sin definir'}",
                      "pon DATA__UNIVERSE_FILE=config/universe-10etf.json en .env"))
    strat = settings.strategy.name
    out.append(_check("estrategia", strat == "pipeline", f"estrategia: {strat}",
                      "pon STRATEGY__NAME=pipeline (sma_crossover fue rechazada por la investigación)"))

    # 3. Seguridad.
    ks = Path(settings.risk.killswitch_file).exists()
    out.append(_check("kill_switch", not ks, "kill switch activo" if ks else "kill switch apagado",
                      "revisa la causa en data/alerts.jsonl y luego `ibtrader clear-kill`"))
    out.append(_check("modo", settings.mode.upper() == "PAPER", f"MODE={settings.mode}",
                      "MODE=PAPER hasta pasar el scorecard"))

    # 4. Freeze: en sombra solo avisa; en órdenes paper bloquea.
    fr = verify_freeze(data / "paper_config_freeze.json", settings)
    out.append(_check("freeze", bool(fr.get("ok")),
                      "configuración congelada vigente" if fr.get("ok")
                      else f"freeze: {fr.get('reason')} {fr.get('changed_sections') or ''}".strip(),
                      "si los cambios son intencionados: `ibtrader config-freeze --write --force`",
                      sombra=False))

    # 5. Claude (opcional): solo si el copiloto o el triage están encendidos.
    wants_ai = settings.ops.copilot or settings.ops.ai_triage
    if wants_ai:
        problem = puerta_config_error()
        token_file = Path(os.environ.get("IBTRADER_PUERTA_TOKEN_FILE") or DEFAULT_PUERTA_TOKEN_FILE)
        ok_ai = problem is None or token_file.is_file()
        detalle = ("puerta configurada en este proceso" if problem is None
                   else f"token de la puerta en {token_file}" if token_file.is_file() else problem)
        out.append(_check("claude_puerta", ok_ai, detalle,
                          f"guarda el token pia_… en {token_file} (las tareas lo cargan con run-task.ps1)",
                          sombra=False, paper=False))
    else:
        out.append(_check("claude_puerta", None, "copiloto y triage apagados (OPS__COPILOT=false)",
                          sombra=False, paper=False))

    # 6. Corrida diaria: tareas y latido.
    missing = tasks_missing()
    if missing is None:
        out.append(_check("tareas_programadas", None, "no comprobable fuera de Windows"))
    else:
        out.append(_check("tareas_programadas", not missing,
                          "las 3 tareas están registradas" if not missing else f"faltan: {', '.join(missing)}",
                          "pwsh -File scripts/schedule-run-daily.ps1 -Action Register"))
    hb = Path(settings.ops.heartbeat_file)
    hb_ok: Optional[bool] = None
    hb_txt = "todavía no hay latido (normal antes de la primera corrida)"
    if hb.is_file():
        try:
            ts = datetime.fromisoformat(str(json.loads(hb.read_text(encoding="utf-8")).get("ts")))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_h = (now - ts).total_seconds() / 3600.0
            hb_ok = age_h <= 30.0
            hb_txt = f"último latido hace {age_h:.0f} h"
        except (OSError, ValueError, json.JSONDecodeError):
            hb_ok, hb_txt = False, "latido ilegible"
    out.append(_check("latido", hb_ok, hb_txt, "revisa data/logs/ibtrader-run-daily-plan.log", sombra=False))

    # 7. IBKR: Gateway y permiso de órdenes (solo para paper).
    host, port = settings.ib.host, settings.ib_port()
    gw = port_open(host, port)
    out.append(_check("gateway_ibkr", gw, f"Gateway {'escucha' if gw else 'no responde'} en {host}:{port}",
                      "abre IB Gateway en modo paper, API activada, puerto 4002, solo 127.0.0.1",
                      sombra=False))
    # Un puerto abierto no basta: la cuenta tiene que responder, ser paper y tener saldo.
    if gw and account_probe is not None:
        try:
            shares, cash, acct = account_probe(settings)
            nav = float(cash or 0.0)
            expected = (settings.ib.expected_account or "").strip()
            problems = []
            if not acct:
                problems.append("la cuenta no respondió")
            elif settings.mode.upper() == "PAPER" and not acct.upper().startswith("DU"):
                problems.append(f"la cuenta {_mask(acct)} no parece paper (las de paper empiezan por DU)")
            if expected and acct and acct != expected:
                problems.append(f"cuenta {_mask(acct)} distinta de IB__EXPECTED_ACCOUNT")
            if nav <= 0 and not shares:
                problems.append("saldo 0 y sin posiciones")
            out.append(_check("cuenta_ibkr", not problems,
                              f"cuenta {_mask(acct)}: efectivo {nav:,.2f} USD, {len(shares)} posiciones"
                              + (f" ({'; '.join(problems)})" if problems else ""),
                              "en el portal de IBKR, fondea la cuenta paper (Settings → Paper Trading Account → "
                              "Reset con el capital deseado) y revisa que el Gateway esté en la cuenta DU",
                              sombra=False))
        except Exception as exc:  # noqa: BLE001 - se informa, no se lanza
            out.append(_check("cuenta_ibkr", False, f"la cuenta no respondió: {type(exc).__name__}: {exc}",
                              "reinicia IB Gateway en paper y revisa que la API acepte 127.0.0.1", sombra=False))
    elif gw:  # sin consultar la cuenta no se puede afirmar que esté lista
        out.append(_check("cuenta_ibkr", None, "cuenta no consultada (usa `ibtrader chequeo` sin --sin-ibkr)",
                          sombra=False))
    else:
        out.append(_check("cuenta_ibkr", None, "sin Gateway: no se pudo consultar la cuenta",
                          sombra=False, paper=False))

    mode = settings.execution.mode
    perm_ok, why = execution_permission(settings)
    if mode == "shadow":
        out.append(_check("permiso_ordenes", None,
                          "modo sombra: no se envía nada (EXECUTION__MODE=shadow)", sombra=False, paper=False))
    elif not perm_ok:
        out.append(_check("permiso_ordenes", False, why,
                          "EXECUTION__MODE=paper_orders, TRADING__ALLOW_BROKER_ORDERS=true, MODE=PAPER",
                          sombra=False))
    elif not gw or orders_probe is None:
        # La configuración lo permite, pero sin preguntar a IBKR no se sabe si el Gateway acepta órdenes.
        out.append(_check("permiso_ordenes", None, f"{why}; no se comprobó si el Gateway acepta órdenes",
                          sombra=False))
    else:
        try:
            err = orders_probe(settings)
        except Exception as exc:  # noqa: BLE001 - se informa, no se lanza
            err = f"{type(exc).__name__}: {exc}"
        if err and "321" in err:
            arreglo = ("en IB Gateway: Configure → Settings → API → Settings, desmarca «Read-Only API» "
                       "y reinicia el Gateway")
        else:
            arreglo = "revisa el log del Gateway; la orden de prueba (what-if, no se envía) fue rechazada"
        out.append(_check("permiso_ordenes", err is None,
                          "el Gateway acepta órdenes (prueba what-if, no se envió nada)" if err is None
                          else f"el Gateway rechaza órdenes: {err}", arreglo, sombra=False))

    listo_sombra = all(c["ok"] is not False for c in out if c["necesario_sombra"])
    listo_paper = all(c["ok"] is True or (c["ok"] is None and c["id"] in ("tareas_programadas",))
                      for c in out if c["necesario_paper"])
    pendientes = [c["arreglo"] for c in out if c["ok"] is False and c["arreglo"]]
    return {"listo_sombra": listo_sombra, "listo_paper": listo_paper, "modo_ejecucion": mode,
            "comprobaciones": out, "pendientes": pendientes}


def _tiingo_last_date(token: str) -> str:
    from ..data.providers import TiingoProvider

    meta = TiingoProvider(token, max_retries=1).fetch_metadata("SPY")
    return str(getattr(meta, "end_date", None) or "?")


__all__ = ["run_preflight"]
