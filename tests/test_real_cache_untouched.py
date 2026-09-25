from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod


def _dir_hash(path: str) -> str:
    h = hashlib.sha256()
    p = Path(path)
    if not p.exists():
        return "absent"
    for root, _, files in os.walk(path):
        for f in sorted(files):
            fp = Path(root) / f
            try:
                with open(fp, "rb") as fh:
                    while True:
                        chunk = fh.read(65536)
                        if not chunk:
                            break
                        h.update(chunk)
            except Exception:
                continue
    return h.hexdigest()


def test_real_cache_not_modified(monkeypatch, tmp_path) -> None:
    before = _dir_hash("./data/cache")
    # Force fixture provider and tmp cache
    monkeypatch.setenv("DATA__PROVIDERS", '["fixture"]')
    monkeypatch.setenv("DATA__FIXTURE_DIR", "./tests/fixtures")
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path))
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["backtest-sample", "--exp-id", "cacheguard"])
    assert res.exit_code == 0
    after = _dir_hash("./data/cache")
    assert before == after

