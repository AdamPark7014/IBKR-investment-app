from __future__ import annotations

from ibtrader.config import AppSettings, SlippageConfig
from ibtrader.research.cost_stress import (
    _with_slippage_mult,
    run_cost_ladder_research,
    summarize_cost_fragility,
)


def test_slippage_mult_does_not_mutate_original() -> None:
    s = AppSettings()
    s.slippage = SlippageConfig(bps=1.0)
    stressed = _with_slippage_mult(s, 3.0)
    assert float(s.slippage.bps) == 1.0
    assert float(stressed.slippage.bps) == 3.0


def test_cost_fragility_summary_flags_fragile_pass_then_fail() -> None:
    rows = [
        {
            "params": {"fast": 10, "slow": 30, "slippage_mult": 1.0},
            "cost_ladder_mult": 1.0,
            "gate_passed": True,
        },
        {
            "params": {"fast": 10, "slow": 30, "slippage_mult": 2.0},
            "cost_ladder_mult": 2.0,
            "gate_passed": False,
        },
        {
            "params": {"fast": 10, "slow": 30, "slippage_mult": 3.0},
            "cost_ladder_mult": 3.0,
            "gate_passed": False,
        },
    ]
    frag = summarize_cost_fragility(rows)
    assert len(frag) == 1
    assert frag[0]["fragile"] is True
    assert frag[0]["robust_to_3x"] is False


def test_cost_ladder_research_tags_mults(monkeypatch) -> None:
    # Unit: ensure ladder expands to 3 rows for one candidate without full WF
    calls = []

    def fake_run_sma_research(**kwargs):
        calls.append(kwargs["settings"].slippage.bps)
        return [
            {
                "candidate_id": "x",
                "params": {"fast": 10, "slow": 30},
                "oos": {},
                "buy_hold_oos": None,
                "gate_passed": False,
                "gate_reasons": [],
                "gate_checks": {},
            }
        ]

    monkeypatch.setattr(
        "ibtrader.research.cost_stress.run_sma_research", fake_run_sma_research
    )
    s = AppSettings()
    s.slippage = SlippageConfig(bps=2.0)
    rows = run_cost_ladder_research(
        s, {"SPY": None}, "SPY", candidates=[(10, 30)], multipliers=(1.0, 2.0, 3.0)
    )
    assert len(rows) == 3
    assert calls == [2.0, 4.0, 6.0]
    assert [r["cost_ladder_mult"] for r in rows] == [1.0, 2.0, 3.0]
