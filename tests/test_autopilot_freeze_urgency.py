from __future__ import annotations

from typing import Any

import pandas as pd

import ibtrader.ops.autopilot as ap
from ibtrader.config import AppSettings
from ibtrader.engine.decision import Decision


def test_autopilot_includes_freeze_and_urgency(monkeypatch: Any, tmp_path: Any) -> None:
    s = AppSettings()
    s.data.data_dir = str(tmp_path / "data")
    s.data.reports_dir = str(tmp_path / "reports")
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "reports").mkdir(parents=True)

    monkeypatch.setattr(ap, "load_universe_v2", lambda _s: {"SPY": pd.DataFrame()})
    monkeypatch.setattr(
        ap.DecisionEngine,
        "generate",
        lambda self, _data: [
            Decision(
                symbol="SPY",
                action="WATCH",
                score=0.0,
                confidence=0.0,
                position_size=0.0,
                reason="t",
                regime={},
            )
        ],
    )
    monkeypatch.setattr(ap, "build_market_radar", lambda _d: {"as_of": "2024-01-01", "disclaimer": "Triage only."})

    # No freeze yet: autopilot reports it and does NOT write one (that would re-baseline silently).
    out0 = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    assert out0["orders_sent"] == 0
    assert out0["config_freeze"]["ok"] is False
    assert out0["config_freeze"]["reason"] == "missing_freeze"
    assert not (tmp_path / "data" / "paper_config_freeze.json").exists()
    assert "config_freeze_missing" in {a["code"] for a in out0["alerts"]}

    from ibtrader.ops.config_freeze import write_freeze

    write_freeze(tmp_path / "data" / "paper_config_freeze.json", s)
    out = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    assert out["orders_sent"] == 0
    assert "config_freeze" in out
    assert out["config_freeze"]["ok"] is True
    assert out["urgency"]["mode"] == "passive"
    assert "alerts" in out
    codes = {a["code"] for a in out["alerts"]}
    assert "config_drift" not in codes
    # No paper account: no equity point and the drawdown kill alerts stay off (and say so).
    assert out["paper_equity"]["account_present"] is False
    assert out["paper_equity"]["kill_alerts_active"] is False
    assert "paper_kill_alerts_inactive" in codes

    # Enabling broker orders after the freeze is drift, even though the freeze file exists.
    s.trading.allow_broker_orders = True
    out2 = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    assert out2["config_freeze"]["ok"] is False
    assert out2["config_freeze"]["reason"] == "hash_mismatch"
    assert "trading" in out2["config_freeze"]["changed_sections"]
    drift = [a for a in out2["alerts"] if a["code"] == "config_drift"]
    assert drift and drift[0]["severity"] == "kill_recommend"
