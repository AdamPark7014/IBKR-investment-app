"""Chequeo previo: dice en español qué falta para sombra y para órdenes paper."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ibtrader.config import AppSettings
from ibtrader.ops.config_freeze import write_freeze
from ibtrader.ops.preflight import run_preflight

NOW = datetime(2026, 11, 9, 23, 0, tzinfo=timezone.utc)


def _settings(tmp: Path) -> AppSettings:
    s = AppSettings(_env_file=None)
    s.data.data_dir = str(tmp / "data")
    s.risk.killswitch_file = str(tmp / "data" / "KILL_SWITCH")
    s.ops.heartbeat_file = str(tmp / "data" / "heartbeat.json")
    s.data.tiingo_token = "t"
    s.data.universe_file = "config/universe-10etf.json"
    s.strategy.name = "pipeline"
    return s


def _by_id(rep: dict) -> dict:
    return {c["id"]: c for c in rep["comprobaciones"]}


def test_ready_for_shadow_but_not_paper_without_gateway(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    rep = run_preflight(s, port_open=lambda h, p: False, tasks_missing=lambda: [],
                        tiingo_probe=lambda tok: "2026-11-06", now=NOW)
    c = _by_id(rep)
    assert rep["listo_sombra"] is True and rep["listo_paper"] is False
    assert c["tiingo_responde"]["ok"] is True and "2026-11-06" in c["tiingo_responde"]["detalle"]
    assert c["gateway_ibkr"]["ok"] is False and "4002" in c["gateway_ibkr"]["detalle"]
    assert c["freeze"]["ok"] is False and any("config-freeze" in p for p in rep["pendientes"])


def test_ready_for_paper_with_gateway_and_freeze(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    write_freeze(Path(s.data.data_dir) / "paper_config_freeze.json", s)
    (tmp_path / "data" / "heartbeat.json").write_text(json.dumps({"ts": NOW.isoformat()}))
    rep = run_preflight(s, port_open=lambda h, p: p == 4002, tasks_missing=lambda: [],
                        tiingo_probe=lambda tok: "2026-11-06", account_probe=lambda st: ({}, 50_000.0, "DU123"),
                        now=NOW)
    assert rep["listo_paper"] is True, rep["pendientes"]
    assert _by_id(rep)["latido"]["ok"] is True
    assert _by_id(rep)["cuenta_ibkr"]["ok"] is True
    assert "DU123" not in json.dumps(rep) and "DU...23" in _by_id(rep)["cuenta_ibkr"]["detalle"]


def _paper_ready(tmp: Path) -> AppSettings:
    s = _settings(tmp)
    write_freeze(Path(s.data.data_dir) / "paper_config_freeze.json", s)
    (tmp / "data" / "heartbeat.json").write_text(json.dumps({"ts": NOW.isoformat()}))
    return s


def test_open_port_alone_is_not_ready_for_paper(tmp_path: Path) -> None:
    rep = run_preflight(_paper_ready(tmp_path), port_open=lambda h, p: True, tasks_missing=lambda: [],
                        tiingo_probe=lambda tok: "x", now=NOW)
    assert rep["listo_paper"] is False
    assert _by_id(rep)["cuenta_ibkr"]["ok"] is None


def test_unfunded_account_blocks_paper(tmp_path: Path) -> None:
    rep = run_preflight(_paper_ready(tmp_path), port_open=lambda h, p: True, tasks_missing=lambda: [],
                        tiingo_probe=lambda tok: "x", account_probe=lambda st: ({}, 0.0, "DU123"), now=NOW)
    c = _by_id(rep)["cuenta_ibkr"]
    assert rep["listo_paper"] is False and c["ok"] is False and "saldo 0" in c["detalle"]
    assert rep["listo_sombra"] is True  # la sombra no necesita la cuenta


def test_non_paper_account_blocks_paper(tmp_path: Path) -> None:
    rep = run_preflight(_paper_ready(tmp_path), port_open=lambda h, p: True, tasks_missing=lambda: [],
                        tiingo_probe=lambda tok: "x", account_probe=lambda st: ({}, 1000.0, "U999"), now=NOW)
    c = _by_id(rep)["cuenta_ibkr"]
    assert rep["listo_paper"] is False and "no parece paper" in c["detalle"]


def test_account_probe_error_is_reported_not_raised(tmp_path: Path) -> None:
    def boom(st: AppSettings) -> tuple:
        raise TimeoutError("sin respuesta")

    rep = run_preflight(_paper_ready(tmp_path), port_open=lambda h, p: True, tasks_missing=lambda: [],
                        tiingo_probe=lambda tok: "x", account_probe=boom, now=NOW)
    c = _by_id(rep)["cuenta_ibkr"]
    assert rep["listo_paper"] is False and c["ok"] is False and "sin respuesta" in c["detalle"]


def test_missing_token_tasks_and_bad_strategy_block_shadow(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    s.data.tiingo_token = ""
    s.strategy.name = "sma_crossover"
    rep = run_preflight(s, port_open=lambda h, p: False, tasks_missing=lambda: ["ibtrader-run-daily-plan"], now=NOW)
    c = _by_id(rep)
    assert rep["listo_sombra"] is False
    assert c["tiingo_token"]["ok"] is False and c["tiingo_responde"]["ok"] is None
    assert c["estrategia"]["ok"] is False and c["tareas_programadas"]["ok"] is False


def test_tiingo_failure_is_reported_not_raised(tmp_path: Path) -> None:
    def boom(tok: str) -> str:
        raise RuntimeError("401")

    rep = run_preflight(_settings(tmp_path), port_open=lambda h, p: False, tasks_missing=lambda: None,
                        tiingo_probe=boom, now=NOW)
    c = _by_id(rep)
    assert c["tiingo_responde"]["ok"] is False and "401" in c["tiingo_responde"]["detalle"]
    assert c["tareas_programadas"]["ok"] is None


def test_every_command_is_registered_before_the_main_guard() -> None:
    src = Path("src/ibtrader/ops/cli.py").read_text(encoding="utf-8")
    assert src.rfind("@app.command") < src.index('if __name__ == "__main__":')


def _orders_settings(tmp: Path) -> AppSettings:
    s = _paper_ready(tmp)
    s.execution.mode = "paper_orders"
    s.trading.allow_broker_orders = True
    write_freeze(Path(s.data.data_dir) / "paper_config_freeze.json", s)
    return s


def _run_orders(tmp: Path, probe: object) -> dict:
    return run_preflight(_orders_settings(tmp), port_open=lambda h, p: True, tasks_missing=lambda: [],
                         tiingo_probe=lambda tok: "x", account_probe=lambda st: ({}, 1000.0, "DU123"),
                         orders_probe=probe, now=NOW)  # type: ignore[arg-type]


def test_read_only_gateway_blocks_paper_orders(tmp_path: Path) -> None:
    rep = _run_orders(tmp_path, lambda st: "321 Error validating request: API is read-only")
    c = _by_id(rep)["permiso_ordenes"]
    assert rep["listo_paper"] is False and c["ok"] is False and "Read-Only API" in c["arreglo"]


def test_gateway_accepting_whatif_is_ready_for_orders(tmp_path: Path) -> None:
    rep = _run_orders(tmp_path, lambda st: None)
    assert _by_id(rep)["permiso_ordenes"]["ok"] is True
    assert rep["listo_paper"] is True, rep["pendientes"]


def test_config_permission_alone_is_not_enough(tmp_path: Path) -> None:
    rep = _run_orders(tmp_path, None)
    assert _by_id(rep)["permiso_ordenes"]["ok"] is None and rep["listo_paper"] is False


def test_no_module_imports_the_old_ib_insync_package() -> None:
    # La función que habla con IBKR se simula en los tests; un import roto solo se vería en la PC.
    offenders = [str(p) for p in Path("src").rglob("*.py") if "import ib_insync" in p.read_text(encoding="utf-8")
                 or "from ib_insync" in p.read_text(encoding="utf-8")]
    assert offenders == []
