"""Phase-2 portfolio research runner and the ``research-portfolio`` CLI command."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
import ibtrader.research.portfolio_runner as pr
from ibtrader.config import AppSettings
from ibtrader.data.universe import UniverseEntry, UniverseSpec, load_universe_spec
from ibtrader.research.portfolio_runner import (
    RECOMMENDATION_FAIL,
    RECOMMENDATION_PASS,
    portfolio_candidates,
    run_portfolio_research,
    sixty_forty_legs,
)
from tests.test_pipeline_system import BOXES, SYNTH, make_synthetic

ASSET_CLASS = {
    "us_equity": "equity",
    "treasuries_intermediate": "fixed_income",
    "treasuries_long": "fixed_income",
    "gold": "commodity",
    "commodities": "commodity",
    "reit": "real_estate",
}


def synthetic_universe() -> UniverseSpec:
    entries = [
        UniverseEntry(symbol=sym, asset_class=ASSET_CLASS[box], box=box, listed_from=None, spread_bps=2.0)
        for sym, (box, _mu, _sigma) in SYNTH.items()
    ]
    return UniverseSpec(name="synthetic-6", entries=entries, as_of="2026-10-21")


def universe_json() -> Dict[str, Any]:
    return {
        "name": "synthetic-6",
        "as_of": "2026-10-21",
        "source": "tests/test_portfolio_runner_cli.py",
        "symbols": [
            {
                "symbol": sym,
                "asset_class": ASSET_CLASS[box],
                "box": box,
                "listed_from": "2000-01-03",
                "delisted_on": None,
                "spread_bps": 2.0,
            }
            for sym, (box, _mu, _sigma) in SYNTH.items()
        ],
    }


def _settings(tmp_path: Path) -> AppSettings:
    s = AppSettings()
    s.data.reports_dir = str(tmp_path / "reports")
    s.risk.killswitch_file = str(tmp_path / "KILL_SWITCH")
    s.universe.symbols = list(SYNTH)
    s.universe.benchmark = "SPY"
    return s


@pytest.fixture(scope="module")
def synthetic() -> Dict[str, pd.DataFrame]:
    return make_synthetic()


@pytest.fixture(scope="module")
def smoke_summary(synthetic: Dict[str, pd.DataFrame], tmp_path_factory: pytest.TempPathFactory) -> Dict[str, Any]:
    tmp = tmp_path_factory.mktemp("smoke")
    s = _settings(tmp)
    return run_portfolio_research(
        synthetic, s, synthetic_universe(), profile="smoke", exp_id="p2_smoke", reports_dir=s.data.reports_dir
    )


# --------------------------------------------------------------------------- runner


def test_portfolio_candidates_profiles() -> None:
    smoke = portfolio_candidates("smoke")
    assert len(smoke) == 1
    assert smoke[0][2] == "box_inverse_vol"
    full = portfolio_candidates("full")
    assert len(full) > 1
    assert len({c[0] for c in full}) == len(full)
    assert {c[2] for c in full} == {"box_inverse_vol", "hrp", "equal"}
    with pytest.raises(ValueError):
        portfolio_candidates("nope")


def test_sixty_forty_legs_prefers_spy_ief_then_boxes() -> None:
    uni = synthetic_universe()
    assert sixty_forty_legs(list(SYNTH), uni) == ("SPY", "IEF")
    assert sixty_forty_legs(["VNQ", "TLT", "GLD"], uni) == ("VNQ", "TLT")
    assert sixty_forty_legs(["GLD", "PDBC"], None) == ("GLD", "PDBC")


def test_run_portfolio_research_smoke_summary(smoke_summary: Dict[str, Any]) -> None:
    out = smoke_summary
    assert out["verdict"] in {"PASS", "FAIL"}
    assert out["n_trials"] == 1
    assert out["n_candidates"] == 1
    assert out["profile"] == "smoke"
    if out["verdict"] == "FAIL":
        assert out["recommendation"] == RECOMMENDATION_FAIL
        assert "indexar" in out["recommendation"]
    else:
        assert out["recommendation"].startswith(RECOMMENDATION_PASS)
    bench = out["benchmarks"]
    assert bench is not None
    assert "sixty_forty" in bench and "all_weather" in bench and "random" in bench
    sf = bench["sixty_forty"]["stats"]
    assert {"sharpe", "max_dd"} <= set(sf)
    assert bench["sixty_forty"]["equity"] == "SPY" and bench["sixty_forty"]["bonds"] == "IEF"
    assert bench["all_weather"] is not None, bench.get("all_weather_error")
    assert bench["random"]["n"] == 100
    assert "sharpes" not in bench["random"]
    pct = out["random_sharpe_percentile"]
    assert pct is not None and 0.0 <= pct <= 100.0
    assert out["warmup_end"] is not None
    assert out["cost_drag_annual_pct"] is not None and out["cost_drag_annual_pct"] >= 0.0
    assert out["turnover"] is not None and out["turnover"] >= 0.0
    cand = out["candidates"][0]
    assert cand["gate_passed"] is (out["verdict"] == "PASS")
    assert cand["oos"]["trade_count"] >= 1
    assert cand["gate_checks"]["gate_mode"] == "strict"
    assert cand["buy_hold_oos"]["sharpe"] == sf["sharpe"]
    assert 0.0 <= cand["restricted_bar_frac"] <= 1.0


def test_run_portfolio_research_registry_rows_and_artifact(smoke_summary: Dict[str, Any]) -> None:
    out = smoke_summary
    rows = out["registry_records"]
    assert len(rows) == 1
    rec = rows[0]
    assert rec["exp_id"] == "p2_smoke"
    assert rec["candidate_id"] == "pipeline_default_box_inverse_vol"
    assert len(rec["dataset_hash"]) == 64 and len(rec["config_hash"]) == 64
    assert rec["n_trials"] == 1
    assert rec["params"]["family"] == "pipeline"
    assert rec["buy_hold_oos"] is not None
    assert rec["gate_passed"] is (out["verdict"] == "PASS")
    assert out["dataset_hash"] == rec["dataset_hash"]
    art = Path(out["artifact"])
    assert art.name == "portfolio_p2_smoke.json"
    on_disk = json.loads(art.read_text(encoding="utf-8"))
    assert on_disk["verdict"] == out["verdict"]
    assert on_disk["n_trials"] == 1
    assert "sharpes" not in json.dumps(on_disk["benchmarks"]["random"])


def test_run_portfolio_research_full_profile_counts_trials(
    synthetic: Dict[str, pd.DataFrame], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep the test fast: a 2-configuration grid and fewer random portfolios, but still > 1 trial.
    monkeypatch.setattr(pr, "INSTRUMENT_WEIGHTINGS", ("box_inverse_vol", "equal"))
    monkeypatch.setattr(pr, "rule_sets", lambda: {"ewmac": ("ewmac16_64", "ewmac32_128", "ewmac64_256")})
    monkeypatch.setitem(pr.RANDOM_PORTFOLIOS, "full", 30)
    s = _settings(tmp_path)
    out = run_portfolio_research(synthetic, s, synthetic_universe(), profile="full", exp_id="p2_full",
                                 reports_dir=s.data.reports_dir)
    assert out["n_trials"] == 2
    assert out["n_candidates"] == 2
    assert {c["candidate_id"] for c in out["candidates"]} == {"pipeline_ewmac_box_inverse_vol", "pipeline_ewmac_equal"}
    assert all(r["n_trials"] == 2 for r in out["registry_records"])
    assert out["years_needed"] > 0.0
    assert out["budget"]["n_trials"] == 2
    assert out["benchmarks"]["random"]["n"] == 30
    assert out["best_candidate"] in {c["candidate_id"] for c in out["candidates"]}


def test_holdout_hides_bars_from_the_oos_window(synthetic: Dict[str, pd.DataFrame], tmp_path: Path) -> None:
    idx = synthetic["SPY"].index
    holdout_start = str(idx[-200].date())
    s = _settings(tmp_path)
    s.research.holdout_start = holdout_start
    s.research.confirmation_mode = False
    out = run_portfolio_research(synthetic, s, synthetic_universe(), profile="smoke", exp_id="p2_holdout",
                                 reports_dir=s.data.reports_dir)
    cut = pd.Timestamp(holdout_start)
    assert out["holdout_applied"] is True
    assert out["holdout_opened"] is False
    assert out["n_bars_hidden"] == 200
    assert pd.Timestamp(out["data_end"]) < cut
    assert pd.Timestamp(out["oos_end"]) < cut
    for cand in out["candidates"]:
        assert pd.Timestamp(cand["oos_end"]) < cut
        assert pd.Timestamp(cand["warmup_end"]) < cut
    rec = out["registry_records"][0]
    assert rec["holdout_start"] == holdout_start and rec["holdout_applied"] is True


# --------------------------------------------------------------------------- CLI


def _write_fixture_dir(data: Dict[str, pd.DataFrame], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sym, df in data.items():
        frame = df[["open", "high", "low", "close", "volume"]].copy()
        frame.index = pd.DatetimeIndex(frame.index).strftime("%Y-%m-%d")
        frame.to_csv(directory / f"{sym}_1d.csv", index_label="date")


def _json_payload(stdout: str) -> Dict[str, Any]:
    lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
    assert lines, stdout
    return json.loads(lines[-1])


def test_research_portfolio_cli_smoke(synthetic: Dict[str, pd.DataFrame], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_dir = tmp_path / "fixtures"
    _write_fixture_dir(synthetic, fixture_dir)
    universe_path = tmp_path / "universe.json"
    universe_path.write_text(json.dumps(universe_json()), encoding="utf-8")
    assert load_universe_spec(universe_path).symbols == list(SYNTH)

    monkeypatch.setenv("DATA__PROVIDERS", '["fixture"]')
    monkeypatch.setenv("DATA__FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("DATA__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DATA__JOURNAL_DB", str(tmp_path / "data" / "journal.sqlite"))
    monkeypatch.setenv("RISK__KILLSWITCH_FILE", str(tmp_path / "KILL_SWITCH"))

    runner = CliRunner(mix_stderr=False)
    res = runner.invoke(
        cli_mod.app,
        ["research-portfolio", "--profile", "smoke", "--universe", str(universe_path), "--exp-id", "p2_cli"],
    )
    assert res.exit_code == 0, res.stdout + (res.stderr or "") + repr(res.exception)
    payload = _json_payload(res.stdout)
    assert payload["verdict"] in {"PASS", "FAIL"}
    assert payload["n_trials"] == 1
    assert payload["symbols"] == list(SYNTH)
    assert payload["boxes"] == BOXES
    assert payload["profile"] == "smoke"
    assert payload["holdout_applied"] is False
    if payload["verdict"] == "FAIL":
        assert RECOMMENDATION_FAIL in (res.stderr or "")
    registry = Path(payload["registry"])
    assert registry.exists()
    lines = [ln for ln in registry.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["exp_id"] == "p2_cli" and len(row["dataset_hash"]) == 64
    art = Path(payload["artifact"])
    assert art.exists() and art.name == "portfolio_p2_cli.json"
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    assert pd.Timestamp(payload["data_end"]) <= today
