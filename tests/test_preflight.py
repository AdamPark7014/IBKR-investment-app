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
                        tiingo_probe=lambda tok: "2026-11-06", now=NOW)
    assert rep["listo_paper"] is True, rep["pendientes"]
    assert _by_id(rep)["latido"]["ok"] is True


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
