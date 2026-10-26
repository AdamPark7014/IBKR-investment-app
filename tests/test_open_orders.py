from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ibtrader.ops.cli import app as cli_mod_app
from ibtrader.ops.open_orders import load_touchable, summary, write_sample


def test_write_sample_shape(tmp_path: Path) -> None:
    p = write_sample(tmp_path / "paper_open_orders.json")
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "age_seconds" not in data
    assert isinstance(data.get("orders"), list) and len(data["orders"]) == 1
    assert data["orders"][0]["symbol"] == "SPY"
    assert str(data["orders"][0]["opened_at"]).endswith("Z")


def test_load_touchable_default_true(tmp_path: Path) -> None:
    assert load_touchable(tmp_path / "missing.json") is True
    p = tmp_path / "o.json"
    p.write_text('{"orders":[]}', encoding="utf-8")
    assert load_touchable(p) is True


def test_load_touchable_false(tmp_path: Path) -> None:
    p = tmp_path / "o.json"
    p.write_text('{"touchable": false, "orders":[]}', encoding="utf-8")
    assert load_touchable(p) is False
    p.write_text('{"touchable": "false"}', encoding="utf-8")
    assert load_touchable(p) is False


def test_summary_fields(tmp_path: Path) -> None:
    p = tmp_path / "o.json"
    p.write_text(
        '{"orders":[{"symbol":"SPY","opened_at":"2026-10-24T12:00:00Z"}],"touchable":true}',
        encoding="utf-8",
    )
    out = summary(p)
    assert set(out) >= {"age_seconds", "touchable", "orders_sent", "n_orders"}
    assert out["orders_sent"] == 0
    assert out["n_orders"] == 1
    assert out["touchable"] is True
    assert out["age_seconds"] >= 0.0


def test_summary_missing(tmp_path: Path) -> None:
    out = summary(tmp_path / "nope.json")
    assert out["orders_sent"] == 0
    assert out["n_orders"] == 0
    assert out["touchable"] is True
    assert out["age_seconds"] == 0.0


def test_open_orders_cli(tmp_path: Path) -> None:
    p = tmp_path / "paper_open_orders.json"
    runner = CliRunner()
    res_w = runner.invoke(cli_mod_app, ["open-orders", "--write-sample", "--path", str(p)])
    assert res_w.exit_code == 0, res_w.stdout + str(res_w.exception)
    w = json.loads(res_w.stdout)
    assert w["orders_sent"] == 0
    assert w["n_orders"] == 1
    assert w["sample"] is True
    # The sample never lands in the operational file the autopilot reads.
    assert not p.is_file()
    assert (tmp_path / "paper_open_orders.sample.json").is_file()

    res = runner.invoke(cli_mod_app, ["open-orders", "--path", str(p)])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    out = json.loads(res.stdout)
    assert out["orders_sent"] == 0
    assert out["n_orders"] == 0
    assert "age_seconds" in out
    assert "touchable" in out


def test_sample_payload_is_ignored_by_triage(tmp_path: Path) -> None:
    from ibtrader.ops.urgency_age import load_open_order_age_seconds

    p = tmp_path / "paper_open_orders.json"
    p.write_text(
        '{"sample": true, "touchable": false, "orders":[{"symbol":"SPY","opened_at":"2020-01-01T00:00:00Z"}]}',
        encoding="utf-8",
    )
    # A years-old fake order would force "aggressive" urgency forever; samples count as nothing.
    assert load_open_order_age_seconds(p) == 0.0
    assert load_touchable(p) is True
    assert summary(p)["sample"] is True
