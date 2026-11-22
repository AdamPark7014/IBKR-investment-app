"""Respaldo del estado de paper y seguimiento de paper contra el modelo."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ibtrader.config import AppSettings
from ibtrader.ops.paper_curve import REAL_BASES, load_equity_points
from ibtrader.ops.respaldo import backup_state
from ibtrader.ops.seguimiento import MIN_DAYS, compare, paper_equity


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    monkeypatch.delenv("IBTRADER_RESPALDO_DIR", raising=False)
    s = AppSettings()
    s.data.data_dir = str(tmp_path / "data")
    (tmp_path / "data" / "cache").mkdir(parents=True)
    (tmp_path / "data" / "paper_account.json").write_text('{"cash": 1}', encoding="utf-8")
    (tmp_path / "data" / "paper_equity.jsonl").write_text('{"ts": "x"}\n', encoding="utf-8")
    (tmp_path / "data" / "cache" / "SPY.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "vigia.lock").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "nota.txt").write_text("no entra", encoding="utf-8")
    return s


def test_respaldo_guarda_solo_el_estado_y_rota(settings: AppSettings) -> None:
    for d in (1, 2, 3):
        res = backup_state(settings, date(2026, 11, d), keep=2)
        assert res["ok"] and res["n_archivos"] == 2
    out = Path(settings.data.data_dir) / "respaldos"
    assert sorted(p.name for p in out.iterdir()) == ["estado-20261102.zip", "estado-20261103.zip"]
    with zipfile.ZipFile(out / "estado-20261103.zip") as z:
        assert sorted(z.namelist()) == ["paper_account.json", "paper_equity.jsonl"]


def test_respaldo_sin_estado_no_falla(tmp_path: Path) -> None:
    s = AppSettings()
    s.data.data_dir = str(tmp_path / "vacio")
    assert backup_state(s, date(2026, 11, 1))["ok"] is False


def test_respaldo_respeta_la_carpeta_elegida(settings: AppSettings, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBTRADER_RESPALDO_DIR", str(tmp_path / "otro_disco"))
    assert backup_state(settings, date(2026, 11, 1))["ok"]
    assert (tmp_path / "otro_disco" / "estado-20261101.zip").is_file()


def test_paper_equity_usa_el_ultimo_punto_del_dia() -> None:
    pts = [{"ts": "2026-11-09T10:00", "equity": 100.0}, {"ts": "2026-11-09T18:00", "equity": 101.0},
           {"ts": "2026-11-10T18:00", "equity": 102.01}]
    eq = paper_equity(pts)
    assert list(eq) == [101.0, 102.01]


def test_los_puntos_del_broker_cuentan_como_capital_real(tmp_path: Path) -> None:
    p = tmp_path / "eq.jsonl"
    p.write_text('{"ts": "2026-11-09", "equity": 100.0, "basis": "broker"}\n'
                 '{"ts": "2026-11-10", "equity": 101.0, "basis": "shadow"}\n', encoding="utf-8")
    assert [x["basis"] for x in load_equity_points(p, bases=REAL_BASES)] == ["broker"]


def test_compare_veredictos() -> None:
    idx = pd.bdate_range("2026-01-01", periods=61)
    rng = np.random.default_rng(0)
    model = pd.Series(rng.normal(0.0003, 0.004, 61), index=idx)
    ideal = (1.0 + model).cumprod() * 100.0
    assert compare(ideal.iloc[:5], model)["veredicto"] == "insuficiente"
    assert compare(pd.Series(dtype=float), model)["veredicto"] == "insuficiente"
    ok = compare(ideal, model)
    assert ok["veredicto"] == "sigue_al_modelo" and ok["n_intervalos"] == 60 >= MIN_DAYS
    assert abs(ok["diferencia"]) < 1e-12
    lejos = compare(pd.Series(100.0, index=idx), model)  # cartera vacía: no sigue al modelo
    assert lejos["veredicto"] == "revisar" and lejos["retorno_paper"] == 0.0


def test_compare_con_huecos_usa_el_retorno_compuesto_del_intervalo() -> None:
    idx = pd.bdate_range("2026-01-01", periods=10)
    model = pd.Series(0.01, index=idx)
    ideal = (1.0 + model).cumprod() * 100.0
    out = compare(ideal.iloc[[0, 3, 9]], model)  # paper solo tiene 3 puntos: dos intervalos de 3 y 6 días
    assert out["n_intervalos"] == 2 and out["dias_por_intervalo"] == 4.5
    assert abs(out["diferencia"]) < 1e-12
