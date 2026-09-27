from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.research.market_analyzer import analyze_market
from ibtrader.research.panel import render_warden_panel, write_warden_panel


def _mk(len_days: int = 450, seed: float = 0.0) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    t = pd.Series(range(len(idx)), index=idx).astype(float)
    wiggle = ((t % 30) - 15) * 0.35
    px = (100.0 + seed + 0.05 * t + wiggle).astype(float)
    return pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1000.0 + t},
        index=idx,
    )


def test_warden_model_has_engines_and_confidence() -> None:
    data = {"SPY": _mk(seed=0), "QQQ": _mk(seed=4), "IWM": _mk(seed=-2)}
    rep = analyze_market(data, benchmark="SPY")
    assert rep["model"]["name"] == "WARDEN-X9"
    assert len(rep["model"]["engines"]) >= 12
    assert "search_intensity" in rep["model"]
    assert "posture" in rep
    assert "sleeve_hypothesis" in rep
    assert "top_opportunity" in rep
    row = rep["ranked"][0]
    assert "engines" in row
    assert len(row["engines"]) >= 12
    assert "confidence" in row["scores"]
    assert "opportunity" in row["scores"]
    assert "disagreement" in row["scores"]


def test_render_warden_panel_html(tmp_path: Path) -> None:
    data = {"SPY": _mk(seed=0), "QQQ": _mk(seed=3)}
    rep = analyze_market(data, benchmark="SPY")
    doc = render_warden_panel(rep)
    assert "<!DOCTYPE html>" in doc
    assert "WARDEN" in doc
    assert "Engine matrix" in doc
    assert "Triage board" in doc
    assert "NOT a buy list" in doc or "NOT a guarantee" in doc
    path = write_warden_panel(rep, str(tmp_path / "warden.html"))
    assert Path(path).is_file()
    assert "WARDEN" in Path(path).read_text(encoding="utf-8")


def test_research_panel_cli(monkeypatch, tmp_path: Path) -> None:
    def fake_loader(settings):
        return {sym: _mk() for sym in settings.universe.symbols}

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path / "reports"))

    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["research-panel", "--exp-id", "warden_smoke"])
    assert res.exit_code == 0, res.stdout + (res.stderr or "") + str(res.exception)
    import json
    import re

    m = re.search(r"\{(.|\n)*\}$", res.stdout)
    assert m, res.stdout
    payload = json.loads(m.group(0))
    assert payload.get("phase") == "V3-warden-panel"
    panel = Path(payload["panel"])
    assert panel.is_file()
    html = panel.read_text(encoding="utf-8")
    assert "WARDEN" in html
    assert "Syne" in html
