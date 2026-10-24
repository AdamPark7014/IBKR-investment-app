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

    out = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    assert out["orders_sent"] == 0
    assert "config_freeze" in out
    assert out["config_freeze"]["ok"] is True
    assert out["urgency"]["mode"] == "passive"
    assert "alerts" in out
