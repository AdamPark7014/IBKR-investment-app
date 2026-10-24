from __future__ import annotations

from ibtrader.config import AppSettings
from ibtrader.ops.config_freeze import config_hash, snapshot_settings, verify_freeze, write_freeze


def test_config_freeze_roundtrip(tmp_path) -> None:
    s = AppSettings()
    path = tmp_path / "paper_freeze.json"
    payload = write_freeze(path, s)
    assert len(payload["hash"]) == 16
    assert payload["hash"] == config_hash(snapshot_settings(s))
    v = verify_freeze(path, s)
    assert v["ok"] is True
