from __future__ import annotations
import json
from typer.testing import CliRunner
import ibtrader.ops.cli as cli_mod
from ibtrader.ops.ibc_checklist import build_ibc_checklist

def test_build_ibc_checklist_shape() -> None:
    payload = build_ibc_checklist()
    assert payload['phase'] == 'paper-ops'
    assert 'disclaimer' in payload and payload['disclaimer']
    items = payload['items']
    assert len(items) >= 5
    ids = {i['id'] for i in items}
    for key in ('id','title','done_hint','critical'):
        assert all(key in i for i in items)
    assert all(isinstance(i['critical'], bool) for i in items)
    for need in ('gateway_paper_port','api_127_only','no_live_until_phase3_pass','autopilot_scheduled_zero_orders'):
        assert need in ids

def test_ibc_checklist_cli_smoke() -> None:
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ['ibc-checklist'])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    payload = json.loads(res.stdout)
    assert payload['phase'] == 'paper-ops'
    assert len(payload['items']) >= 5
    assert payload.get('disclaimer')