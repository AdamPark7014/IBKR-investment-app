from __future__ import annotations
import json
from typer.testing import CliRunner
import ibtrader.ops.cli as cli_mod
from ibtrader.ops.ibc_checklist import build_ibc_checklist


def test_build_ibc_checklist_shape():
    checklist = build_ibc_checklist()
    assert checklist.phase == 'paper-ops'
    assert len(checklist.items) >= 5
    payload = getattr(checklist, 'payload', {})
    assert 'disclaimer' in payload and bool(payload.get('disclaimer'))
    for item in checklist.items:
        assert hasattr(item, 'id')
        assert hasattr(item, 'title')
        assert hasattr(item, 'done_hint')
        assert hasattr(item, 'critical')
        assert isinstance(item.critical, bool)
    preferred_ids = {'gateway_paper_port', 'api_127_only', 'no_live_until_phase3_pass', 'autopilot_scheduled_zero_orders'}
    found_ids = {item.id for item in checklist.items if item.id in preferred_ids}
    assert found_ids == preferred_ids


def test_ibc_checklist_cli_smoke():
    runner = CliRunner()
    result = runner.invoke(cli_mod.app, ['ibc-checklist'])
    assert result.exit_code == 0
    output_data = json.loads(result.stdout)
    assert output_data['phase'] == 'paper-ops'
    assert len(output_data['items']) >= 5
    assert 'disclaimer' in output_data and bool(output_data.get('disclaimer'))