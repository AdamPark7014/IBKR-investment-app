from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ibtrader.ops.cli import app as cli_mod_app


def test_paper_equity_cli(tmp_path: Path) -> None:
    equity = tmp_path / "paper_equity.jsonl"
    runner = CliRunner()

    # empty / missing path
    res0 = runner.invoke(cli_mod_app, ["paper-equity", "--path", str(equity)])
    assert res0.exit_code == 0, res0.stdout + str(res0.exception)
    p0 = json.loads(res0.stdout)
    assert p0["n_points"] == 0
    assert p0["max_dd"] is None
    assert p0["last_equity"] is None
    assert p0["orders_sent"] == 0

    # append points that create classic DD 100->80->90 => max_dd 0.2
    for eq in (100.0, 80.0, 90.0):
        res = runner.invoke(cli_mod_app, ["paper-equity", "--path", str(equity), "--append", str(eq)])
        assert res.exit_code == 0, res.stdout + str(res.exception)

    resf = runner.invoke(cli_mod_app, ["paper-equity", "--path", str(equity)])
    assert resf.exit_code == 0, resf.stdout + str(resf.exception)
    pf = json.loads(resf.stdout)
    assert pf["n_points"] == 3
    assert pf["last_equity"] == 90.0
    assert abs(pf["max_dd"] - 0.2) < 1e-9
    assert pf["orders_sent"] == 0
    assert equity.is_file()
