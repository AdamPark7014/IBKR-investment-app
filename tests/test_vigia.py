"""Vigía: recupera el plan o la ejecución que se perdió por tener la laptop apagada."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import pytest

from ibtrader.config import AppSettings
from ibtrader.ops.run_daily import Paths
from ibtrader.ops.vigia import MAX_EXECUTE_ATTEMPTS, decide, lock_path, state_path, tick

ET = ZoneInfo("America/New_York")


def _et(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=ET)


@pytest.fixture()
def settings(tmp_path: Path) -> AppSettings:
    s = AppSettings()
    s.data.data_dir = str(tmp_path / "data")
    s.data.reports_dir = str(tmp_path / "reports")
    s.ops.alerts_file = str(tmp_path / "data" / "alerts.jsonl")
    s.execution.mode = "paper_orders"
    return s


def _plan(s: AppSettings, session: str, **extra: Any) -> None:
    p = Paths.from_settings(s)
    p.reports.mkdir(parents=True, exist_ok=True)
    (p.reports / f"{session}-plan.json").write_text(json.dumps({"status": "ok", **extra}), encoding="utf-8")


def _pending(s: AppSettings, run_date: str) -> None:
    p = Paths.from_settings(s)
    p.pending.parent.mkdir(parents=True, exist_ok=True)
    p.pending.write_text(json.dumps({"run_date": run_date, "orders": []}), encoding="utf-8")


# 2026-11-20 es viernes; 2026-11-23 es lunes.

def test_plan_perdido_se_recupera_el_fin_de_semana(settings: AppSettings) -> None:
    d = decide(settings, _et(2026, 11, 21, 11), port_open=lambda: False)
    assert (d.action, d.session) == ("plan", "2026-11-20")


def test_no_planea_antes_de_que_haya_datos(settings: AppSettings) -> None:
    assert decide(settings, _et(2026, 11, 20, 17, 30), port_open=lambda: False).action != "plan"
    assert decide(settings, _et(2026, 11, 20, 19, 5), port_open=lambda: False).action == "plan"


def test_plan_hecho_no_se_repite_y_el_fallido_se_reintenta(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    assert decide(settings, _et(2026, 11, 21, 11), port_open=lambda: False).action == "nada"
    _plan(settings, "2026-11-20", status="data_error", started_at=_et(2026, 11, 20, 19).isoformat())
    assert decide(settings, _et(2026, 11, 20, 19, 30), port_open=lambda: False).action == "nada"
    assert decide(settings, _et(2026, 11, 20, 20, 5), port_open=lambda: False).action == "plan"


def test_ejecuta_tarde_si_se_perdio_la_hora(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    _pending(settings, "2026-11-20")
    assert decide(settings, _et(2026, 11, 23, 9, 40), port_open=lambda: True).reason == "espera tras la apertura"
    assert decide(settings, _et(2026, 11, 23, 13, 0), port_open=lambda: True).action == "execute"


def test_gateway_cerrado_no_ejecuta_y_avisa(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    _pending(settings, "2026-11-20")
    d = decide(settings, _et(2026, 11, 23, 9, 0), port_open=lambda: False)
    assert (d.action, d.alert) == ("nada", "gateway_cerrado")


def test_cerca_del_cierre_ya_no_ejecuta(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    _pending(settings, "2026-11-20")
    d = decide(settings, _et(2026, 11, 23, 15, 30), port_open=lambda: True)
    assert (d.action, d.alert) == ("nada", "sesion_perdida")


def test_sombra_y_fin_de_semana_nunca_ejecutan(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    _pending(settings, "2026-11-20")
    assert decide(settings, _et(2026, 11, 22, 11), port_open=lambda: True).action == "nada"
    settings.execution.mode = "shadow"
    assert decide(settings, _et(2026, 11, 23, 11), port_open=lambda: True).action == "nada"


def test_tope_de_intentos(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    _pending(settings, "2026-11-20")
    st = {"execute_attempts": {"2026-11-20": MAX_EXECUTE_ATTEMPTS}}
    d = decide(settings, _et(2026, 11, 23, 11), port_open=lambda: True, state=st)
    assert (d.action, d.alert) == ("nada", "ejecucion_agotada")


def test_tick_avisa_una_sola_vez_y_cuenta_intentos(settings: AppSettings) -> None:
    _plan(settings, "2026-11-20")
    _pending(settings, "2026-11-20")
    calls: List[str] = []

    def run_phase(phase: str) -> Dict[str, Any]:
        calls.append(phase)
        return {"status": "broker_error", "orders_sent": 0}

    for minute in (0, 15):
        tick(settings, run_phase=run_phase, port_open=lambda: False, now=_et(2026, 11, 23, 9, minute))
    alerts = Path(settings.ops.alerts_file).read_text(encoding="utf-8").strip().splitlines()
    assert len(alerts) == 1 and json.loads(alerts[0])["code"] == "gateway_cerrado"
    assert calls == []

    out = tick(settings, run_phase=run_phase, port_open=lambda: True, now=_et(2026, 11, 23, 11))
    assert (out["accion"], out["estado"]) == ("execute", "broker_error")
    assert calls == ["execute"]
    state = json.loads(state_path(settings).read_text(encoding="utf-8"))
    assert state["execute_attempts"] == {"2026-11-20": 1}
    assert not lock_path(settings).exists()


def test_candado_impide_dos_corridas(settings: AppSettings) -> None:
    now = _et(2026, 11, 21, 11)
    lock_path(settings).parent.mkdir(parents=True, exist_ok=True)
    lock_path(settings).write_text(json.dumps({"ts": now.isoformat()}), encoding="utf-8")
    out = tick(settings, run_phase=lambda p: {"status": "ok"}, port_open=lambda: True, now=now)
    assert out["motivo"] == "otra corrida en curso"


def test_resumen_para_el_telefono() -> None:
    from ibtrader.ops.vigia import summary_text

    plan = summary_text("plan", {"run_date": "2026-11-20", "status": "ok", "nav_after": 1_000_000.0,
                                 "pretrade": {"approved": [{}, {}]}, "blocks": []})
    assert "2 órdenes" in plan and "1,000,000 USD" in plan and "Bloqueos" not in plan
    ex = summary_text("execute", {"run_date": "2026-11-20", "status": "ok", "orders_sent": 2, "blocks": ["data"],
                                  "orders": [{"state": "FILLED"}, {"state": "CANCELLED"}]})
    assert "2 órdenes enviadas" in ex and "1 llenadas de 2" in ex and "Bloqueos: data" in ex


def test_chequeo_acepta_vigia_o_tareas_de_hora_fija() -> None:
    from ibtrader.ops.preflight import tasks_problems

    vigia = {"ibtrader-vigia": "ready", "ibtrader-run-daily-plan": "disabled",
             "ibtrader-run-daily-execute": "disabled", "ibtrader-heartbeat-check": "ready"}
    assert tasks_problems(lambda t: vigia[t]) == []
    fijas = {**vigia, "ibtrader-vigia": "missing", "ibtrader-run-daily-plan": "ready",
             "ibtrader-run-daily-execute": "ready"}
    assert tasks_problems(lambda t: fijas[t]) == []
    nada = {**vigia, "ibtrader-vigia": "disabled", "ibtrader-heartbeat-check": "missing"}
    assert len(tasks_problems(lambda t: nada[t])) == 2


def test_mensaje_sin_telegram_no_falla(settings: AppSettings) -> None:
    from ibtrader.ops.notify import send_message

    assert send_message(settings.ops, "hola") is None
    settings.ops.telegram_bot_token, settings.ops.telegram_chat_id = "t", "1"
    sent: List[Dict[str, Any]] = []

    def post(url: str, json: Dict[str, Any], timeout: float) -> Any:
        sent.append(json)
        return type("R", (), {"status_code": 200})()

    assert send_message(settings.ops, "hola", post) == "sent"
    assert sent[0]["text"] == "[ibtrader] hola"
