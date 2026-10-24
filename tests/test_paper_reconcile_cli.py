from __future__ import annotations

import json
from typing import Any

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.engine.decision import Decision


def _empty_universe(_settings: Any) -> dict[str, pd.DataFrame]:
    return {"SPY": pd.DataFrame()}


def test_paper_reconcile_cli_smoke(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli_mod, "load_universe_v2", _empty_universe)

    def _fake_generate(self: Any, _data: dict[str, pd.DataFrame]) -> list[Decision]:
        return [
            Decision(
                symbol="SPY",
                action="BUY",
                score=0.5,
                confidence=0.5,
                position_size=0.12,
                reason="test",
                regime={},
            ),
        ]

    monkeypatch.setattr(cli_mod.DecisionEngine, "generate", _fake_generate)

    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["paper-reconcile"])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    payload = json.loads(res.stdout)
    assert payload["orders_sent"] == 0
    assert payload["tag"] == "paper-reconcile"
    assert payload["n_drift"] >= 1
    lines = payload["lines"]
    assert any(line["symbol"] == "SPY" and line["desired"] == 0.12 for line in lines)
