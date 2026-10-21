from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod


def _mk(len_days: int = 600) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0, index=idx).astype(float)
    wiggle = (pd.Series(range(len(idx)), index=idx) % 40).astype(float)
    wiggle = (wiggle - 20.0) * 0.5
    px = base + wiggle
    return pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0},
        index=idx,
    )


def test_research_run_cli_smoke_profile(monkeypatch, tmp_path):
    from ibtrader.research import multi_asset as multi_asset_mod

    # Keep smoke fast: one symbol, shorter history (still enough for 2-fold WF).
    monkeypatch.setattr(multi_asset_mod, "DEFAULT_RESEARCH_SYMBOLS", ["SPY"])

    def fake_loader(settings):
        return {sym: _mk(len_days=180) for sym in settings.universe.symbols}

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    monkeypatch.setenv("RISK__MAX_POSITION_PCT", "100.0")
    monkeypatch.setenv("RISK__MAX_TOTAL_EXPOSURE_PCT", "100.0")
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    t0 = time.monotonic()
    res = runner.invoke(
        cli_mod.app,
        ["research-run", "--exp-id", "v3_research_smoke", "--profile", "smoke"],
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 60.0, f"smoke research-run took {elapsed:.1f}s"
    assert res.exit_code == 0, res.stdout + (res.stderr or "") + str(res.exception)

    m = re.search(r"\{(.|\n)*\}$", res.stdout)
    assert m, res.stdout
    payload = json.loads(m.group(0))
    assert payload.get("n_candidates") == 1
    assert "smoke" in (payload.get("suite") or "")
    assert payload.get("dsr") is not None
    assert payload.get("embargo_sensitivity") is None
    assert payload.get("pbo") is None
    assert payload.get("cpcv") is None
    assert payload.get("turnover") is None
    assert payload.get("market_analyzer") is None
    assert payload.get("honest_report") is not None
    for c in payload["candidates"]:
        assert c.get("gate") in {"PASS", "FAIL"}
        assert "gate_detail" in c
        assert "params" in c
    assert payload.get("artifact")
    art = payload["artifact"]
    assert art.endswith("research_v3_research_smoke.json")
    with open(art, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["n_candidates"] == 1


def test_market_analyze_cli(monkeypatch, tmp_path):
    def fake_loader(settings):
        return {sym: _mk(400) for sym in settings.universe.symbols}

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["market-analyze"])
    assert res.exit_code == 0, res.stdout + (res.stderr or "") + str(res.exception)
    m = re.search(r"\{(.|\n)*\}$", res.stdout)
    assert m, res.stdout
    payload = json.loads(m.group(0))
    assert payload.get("phase") == "V3-market-analyzer"
    assert "report" in payload
    assert payload["report"]["n_symbols"] >= 1
    text = (payload["report"].get("disclaimer") or payload.get("note") or "")
    assert "NOT a buy list" in text or "NOT" in text
