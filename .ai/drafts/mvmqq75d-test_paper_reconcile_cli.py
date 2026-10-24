import json
from unittest.mock import patch, MagicMock
import pandas as pd

import typer.testing
from ibtrader.engine.decision import Decision
from ibtrader.ops.cli import cli_mod

runner = typer.testing.CliRunner()


def test_paper_reconcile_cli():
    with patch.object(cli_mod, 'load_universe_v2') as mock_load:
        mock_load.return_value = {"SPY": pd.DataFrame()}

        with patch.object(cli_mod.DecisionEngine, 'generate') as mock_generate:
            mock_generate.return_value = Decision(
                symbol="SPY",
                action="BUY",
                position_size=0.12,
                score=0.5,
                confidence=0.5,
                reason="test",
                regime={}
            )

            result = runner.invoke(cli_mod.paper_reconcile)
            assert result.exit_code == 0

            stdout_json = json.loads(result.stdout)
            assert stdout_json['orders_sent'] == 0
            assert stdout_json['tag'] == 'paper-reconcile'
            assert stdout_json['n_drift'] >= 1
            assert stdout_json['SPY']['desired'][0] == 0.12