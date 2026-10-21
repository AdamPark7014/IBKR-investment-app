"""Execution-cost model (COST_MODEL.md): pure functions, engine integration, reports."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ibtrader.backtest.engine import backtest
from ibtrader.backtest.report import save_equity_report
from ibtrader.config import AppSettings, CommissionConfig, RegFeesConfig, SlippageConfig
from ibtrader.execution.costs import (
    commission,
    half_spread,
    impact,
    reg_fees,
    rolling_adv_and_sigma,
    slippage_legacy_bps,
    total_order_cost,
)
from ibtrader.research.cost_stress import _with_slippage_mult
from ibtrader.research.report import build_honest_report
from ibtrader.strategy.base import Strategy

D = date(2026, 10, 21)
ZERO_REG = RegFeesConfig(sec_fee_rate=0.0, finra_taf_per_share=0.0, cat_per_share=0.0)


class FlipDaily(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        sig = pd.Series(1, index=idx)
        sig.iloc[::2] = -1
        return {"SPY": sig}


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        return {sym: pd.Series(1, index=df.index) for sym, df in data.items()}


def _mk_flip(n: int = 40) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=n)
    px = pd.Series(100.0 + 0.05 * np.arange(n), index=idx).astype(float)
    return {"SPY": pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)}


def _mk_linear(n: int = 100) -> dict[str, pd.DataFrame]:
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return {
        "SPY": pd.DataFrame(
            {
                "open": 100 + np.arange(n),
                "high": 101 + np.arange(n),
                "low": 99 + np.arange(n),
                "close": 100 + np.arange(n),
                "volume": 1_000_000,
            },
            index=idx,
        )
    }


def _mk_random_walk(n: int = 120, seed: int = 7, volume: float = 5_000.0) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n)
    rets = rng.normal(0.0, 0.01, size=n)
    px = pd.Series(100.0 * np.cumprod(1.0 + rets), index=idx).astype(float)
    return {"SPY": pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": volume}, index=idx)}


# --------------------------------------------------------------------------- commission


def test_fixed_commission_minimum_dominates_small_orders() -> None:
    cfg = CommissionConfig()
    assert commission(cfg, 10, 100.0) == pytest.approx(1.0)  # 0.05 < 1.00 minimum
    assert commission(cfg, -10, 100.0) == pytest.approx(1.0)  # sells use |shares|
    assert commission(cfg, 1000, 100.0) == pytest.approx(5.0)  # 0.005 * 1000
    assert commission(cfg, 0, 100.0) == 0.0


def test_fixed_commission_capped_at_one_percent_of_value() -> None:
    cfg = CommissionConfig()
    # 10 shares at USD 5 = USD 50 notional -> cap 1 % = 0.50 < USD 1 minimum
    assert commission(cfg, 10, 5.0) == pytest.approx(0.5)
    uncapped = CommissionConfig(max_percent_of_value=0.0)
    assert commission(uncapped, 10, 5.0) == pytest.approx(1.0)
    legacy_ad_valorem = CommissionConfig(percent_of_value=0.1, max_percent_of_value=0.0)
    assert commission(legacy_ad_valorem, 1000, 100.0) == pytest.approx(5.0 + 0.001 * 100_000.0)


def test_tiered_commission_includes_venue_clearing_and_pass_through() -> None:
    cfg = CommissionConfig(model="tiered")
    broker = max(0.35, 0.0035 * 1000)
    venue = (0.0030 + 0.0002) * 1000
    pass_through = (0.000175 + 0.00056) * broker
    assert commission(cfg, 1000, 100.0) == pytest.approx(broker + venue + pass_through)
    # Minimum applies to the broker leg only
    assert commission(cfg, 10, 100.0) == pytest.approx(0.35 + 0.0032 * 10 + 0.000735 * 0.35)


# --------------------------------------------------------------------------- regulatory fees


def test_reg_fees_only_on_sells() -> None:
    cfg = RegFeesConfig()
    assert reg_fees(cfg, 1000, 100.0, D, is_sell=False) == 0.0
    sell = reg_fees(cfg, -1000, 100.0, D, is_sell=True)
    assert sell == pytest.approx(0.0000206 * 100_000.0 + 0.000003 * 1000)


def test_taf_zero_during_pause_and_charged_after() -> None:
    cfg = RegFeesConfig()  # paused through 2026-12-31
    base = 0.0000206 * 100_000.0 + 0.000003 * 1000
    assert reg_fees(cfg, -1000, 100.0, "2026-12-31", True) == pytest.approx(base)
    assert reg_fees(cfg, -1000, 100.0, date(2027, 1, 4), True) == pytest.approx(base + 0.000195 * 1000)
    # Per-order TAF cap
    big = reg_fees(cfg, -100_000, 100.0, pd.Timestamp("2027-02-01"), True)
    assert big == pytest.approx(0.0000206 * 10_000_000.0 + 9.79 + 0.000003 * 100_000)
    never_paused = RegFeesConfig(finra_taf_paused_until=None)
    assert reg_fees(never_paused, -1000, 100.0, D, True) == pytest.approx(base + 0.000195 * 1000)


# --------------------------------------------------------------------------- spread / impact


def test_half_spread_by_symbol_and_default() -> None:
    cfg = SlippageConfig()
    # SPY: 0.5 bp full spread -> 0.25 bp half spread on USD 100k = 2.50
    assert half_spread(cfg, "SPY", 1000, 100.0) == pytest.approx(2.5)
    # Unknown symbol: default 2.0 bp -> 1 bp half spread = 10.00
    assert half_spread(cfg, "XYZ", 1000, 100.0) == pytest.approx(10.0)
    patient = SlippageConfig(half_spread_mult=0.5)
    assert half_spread(patient, "XYZ", -1000, 100.0) == pytest.approx(5.0)


def test_impact_follows_square_root_and_is_zero_without_inputs() -> None:
    cfg = SlippageConfig()  # Y = 0.5, exponent 0.5
    # 100 shares vs ADV 10k = 1 % participation, sigma 1 %: 0.5*0.01*0.1 = 5 bp of USD 10k = 5.00
    base = impact(cfg, 100, 100.0, sigma_daily=0.01, adv_shares=10_000)
    assert base == pytest.approx(5.0)
    # 4x shares -> 4x notional * sqrt(4) participation = 8x cost
    assert impact(cfg, 400, 100.0, sigma_daily=0.01, adv_shares=10_000) == pytest.approx(8.0 * base)
    assert impact(cfg, 100, 100.0, sigma_daily=0.01, adv_shares=None) == 0.0
    assert impact(cfg, 100, 100.0, sigma_daily=None, adv_shares=10_000) == 0.0
    assert impact(cfg, 100, 100.0, sigma_daily=float("nan"), adv_shares=10_000) == 0.0
    assert impact(cfg, 100, 100.0, sigma_daily=0.01, adv_shares=0.0) == 0.0


def test_rolling_adv_and_sigma_are_shifted_one_bar() -> None:
    n = 30
    idx = pd.bdate_range("2024-01-01", periods=n)
    vol = pd.Series(np.arange(1, n + 1, dtype=float) * 100.0, index=idx)
    close = pd.Series(100.0 * np.cumprod(1.0 + np.sin(np.arange(n)) * 0.01), index=idx)
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": vol}, index=idx)
    adv, sigma = rolling_adv_and_sigma(df, adv_window=5, sigma_window=5)
    assert adv.index.equals(df.index) and sigma.index.equals(df.index)
    # Warm-up: first 5 bars have no ADV (4 bars for the window + 1 for the shift)
    assert adv.iloc[:5].isna().all()
    # Bar t uses bars t-5 .. t-1 only (current bar excluded)
    t = 10
    assert adv.iloc[t] == pytest.approx(vol.iloc[t - 5 : t].mean())
    assert adv.iloc[t] != pytest.approx(vol.iloc[t - 4 : t + 1].mean())
    rets = close.pct_change()
    assert sigma.iloc[t] == pytest.approx(rets.iloc[t - 5 : t].std(ddof=0))
    # No volume column -> ADV all NaN, sigma still computed
    adv2, sigma2 = rolling_adv_and_sigma(df.drop(columns=["volume"]), 5, 5)
    assert adv2.isna().all()
    assert sigma2.notna().sum() > 0


# --------------------------------------------------------------------------- order cost


def test_total_order_cost_bps_model_matches_legacy_formulas() -> None:
    sc = SlippageConfig(model="bps", bps=1.0)
    cc = CommissionConfig()
    oc = total_order_cost("SPY", 1000, 100.0, D, commission_cfg=cc, slippage_cfg=sc, reg_fees_cfg=ZERO_REG)
    assert oc.fill_price == pytest.approx(slippage_legacy_bps(sc, 100.0, 1))
    assert oc.fill_price == pytest.approx(100.0 * (1 + 1.0 / 1e4))
    assert oc.commission == pytest.approx(max(0.005 * 1000, 1.0))
    assert oc.impact == 0.0
    assert oc.half_spread == pytest.approx(1000 * 100.0 * 1.0 / 1e4)
    assert oc.reg_fees == 0.0
    assert oc.total == pytest.approx(oc.commission + oc.half_spread)
    assert oc.bps_all_in == pytest.approx(oc.total / oc.notional * 1e4)
    sell = total_order_cost("SPY", -1000, 100.0, D, commission_cfg=cc, slippage_cfg=sc, reg_fees_cfg=ZERO_REG)
    assert sell.fill_price == pytest.approx(100.0 * (1 - 1.0 / 1e4))


def test_total_order_cost_spread_impact_fill_and_breakdown() -> None:
    sc = SlippageConfig()
    cc = CommissionConfig()
    rf = RegFeesConfig()
    buy = total_order_cost(
        "XYZ", 100, 100.0, D, commission_cfg=cc, slippage_cfg=sc, reg_fees_cfg=rf,
        sigma_daily=0.01, adv_shares=10_000,
    )
    hs_frac = 0.5 * 2.0 / 1e4
    imp_frac = 0.5 * 0.01 * math.sqrt(100 / 10_000)
    assert buy.fill_price == pytest.approx(100.0 * (1 + hs_frac + imp_frac))
    assert buy.half_spread == pytest.approx(hs_frac * 10_000.0)
    assert buy.impact == pytest.approx(imp_frac * 10_000.0)
    assert buy.reg_fees == 0.0
    sell = total_order_cost(
        "XYZ", -100, 100.0, D, commission_cfg=cc, slippage_cfg=sc, reg_fees_cfg=rf,
        sigma_daily=0.01, adv_shares=10_000,
    )
    assert sell.fill_price == pytest.approx(100.0 * (1 - hs_frac - imp_frac))
    assert sell.reg_fees > 0.0
    assert sell.total > buy.total - buy.half_spread - buy.impact  # sells carry reg fees
    empty = total_order_cost("XYZ", 0, 100.0, D, commission_cfg=cc, slippage_cfg=sc)
    assert empty.total == 0.0 and empty.fill_price == 100.0


# --------------------------------------------------------------------------- engine


def test_engine_bps_model_reproduces_legacy_golden_run() -> None:
    """Golden values recorded from the engine before the cost model (2026-10-21)."""
    cc = CommissionConfig()
    sc = SlippageConfig(model="bps", bps=1.0)
    flip = backtest(_mk_flip(), FlipDaily(), cc, sc, reg_fees_cfg=ZERO_REG)
    assert float(flip.equity_curve.iloc[-1]) == pytest.approx(98855.13068000007, abs=1e-6)
    assert flip.stats.total_commission == pytest.approx(378.895, abs=1e-9)
    assert flip.stats.trade_count == 39
    lin = backtest(_mk_linear(), AlwaysLong(), cc, sc, reg_fees_cfg=ZERO_REG)
    assert float(lin.equity_curve.iloc[-1]) == pytest.approx(197005.051, abs=1e-6)
    assert lin.stats.total_commission == pytest.approx(4.95, abs=1e-9)
    assert lin.stats.trade_count == 1
    # Legacy slippage is still accounted for in the breakdown, impact is not modelled
    assert flip.stats.total_slippage > 0.0
    assert flip.stats.total_impact == 0.0
    assert flip.stats.total_reg_fees == 0.0


def test_engine_reg_fees_reduce_cash_on_sells_only() -> None:
    cc = CommissionConfig()
    sc = SlippageConfig(model="bps", bps=1.0)
    no_fees = backtest(_mk_flip(), FlipDaily(), cc, sc, reg_fees_cfg=ZERO_REG)
    with_fees = backtest(_mk_flip(), FlipDaily(), cc, sc)  # default RegFeesConfig()
    assert with_fees.stats.total_reg_fees > 0.0
    assert float(with_fees.equity_curve.iloc[-1]) < float(no_fees.equity_curve.iloc[-1])
    # A long-only single entry never sells: no regulatory fees at all
    long_only = backtest(_mk_linear(), AlwaysLong(), cc, sc)
    assert long_only.stats.total_reg_fees == 0.0


def test_engine_spread_impact_costs_exceed_commission() -> None:
    res = backtest(_mk_random_walk(), FlipDaily(), CommissionConfig(), SlippageConfig())
    st = res.stats
    assert st.trade_count > 10
    assert st.n_orders == st.trade_count
    assert st.notional_traded > 0.0
    assert st.total_slippage > 0.0
    assert st.total_impact > 0.0  # ADV/sigma available after the 20-bar warm-up
    assert st.total_reg_fees > 0.0
    assert st.total_costs >= st.total_commission
    assert st.total_costs == pytest.approx(
        st.total_commission + st.total_reg_fees + st.total_slippage + st.total_impact
    )
    assert st.avg_cost_bps_per_order > 0.0
    assert st.avg_cost_bps_per_order == pytest.approx(st.total_costs / st.notional_traded * 1e4)
    # Fills are worse than the reference open on every order
    opens = _mk_random_walk()["SPY"]["open"]
    for d, _sym, qty, fill, _reason in res.trades:
        ref = float(opens.loc[pd.Timestamp(d)])
        assert fill > ref if qty > 0 else fill < ref


def test_engine_cost_drag_annual_pct_is_consistent() -> None:
    initial = 50_000.0
    res = backtest(_mk_random_walk(), FlipDaily(), CommissionConfig(), SlippageConfig(), initial_equity=initial)
    st = res.stats
    years = len(res.returns) / 252.0
    assert st.cost_drag_annual_pct == pytest.approx(st.total_costs / initial / years * 100.0)
    assert st.cost_drag_annual_pct > 0.0
    assert st.turnover == pytest.approx(st.notional_traded / initial)


def test_engine_spread_impact_is_deterministic() -> None:
    r1 = backtest(_mk_random_walk(), FlipDaily(), CommissionConfig(), SlippageConfig())
    r2 = backtest(_mk_random_walk(), FlipDaily(), CommissionConfig(), SlippageConfig())
    assert list(r1.equity_curve.values) == list(r2.equity_curve.values)
    assert r1.trades == r2.trades
    assert r1.stats.total_costs == r2.stats.total_costs


# --------------------------------------------------------------------------- reports


def test_equity_report_embeds_cost_table_and_stats_json(tmp_path: Path) -> None:
    res = backtest(_mk_random_walk(), FlipDaily(), CommissionConfig(), SlippageConfig())
    out = save_equity_report(res, str(tmp_path), name="costs_probe")
    html = Path(out).read_text(encoding="utf-8")
    assert 'id="ibtrader-costs"' in html
    assert "Avg all-in cost per order (bps)" in html
    start = html.index('id="ibtrader-stats">') + len('id="ibtrader-stats">')
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert payload["avg_cost_bps_per_order"] == pytest.approx(res.stats.avg_cost_bps_per_order)
    assert payload["total_costs"] == pytest.approx(res.stats.total_costs)
    assert payload["cost_drag_annual_pct"] == pytest.approx(res.stats.cost_drag_annual_pct)


def _suite(avg_bps: float | None, gate_passed: bool = True) -> dict:
    oos = {"sharpe": 0.8, "turnover": 4.0, "cost_drag_annual_pct": 0.9}
    if avg_bps is not None:
        oos["avg_cost_bps_per_order"] = avg_bps
    return {
        "symbol": "SPY",
        "candidates": [{"candidate_id": "sma_10_30", "gate_passed": gate_passed, "oos": oos}],
        "tracks": {"sma_grid": [{"candidate_id": "sma_10_30", "gate_passed": gate_passed}]},
    }


def test_honest_report_flags_too_cheap_cost_model() -> None:
    rep = build_honest_report(_suite(0.3), commission_cfg=CommissionConfig(), slippage_cfg=SlippageConfig())
    assert rep["cost_model_suspicious"] is True
    assert "0.30 bp" in rep["cost_model_note"]
    assert rep["cost_summary"]["avg_cost_bps_source"] == "observed"
    assert rep["cost_summary"]["sanity_min_all_in_bps"] == pytest.approx(2.5)
    # turnover / drag surface in the summary
    assert rep["turnover"] == pytest.approx(4.0)
    assert rep["cost_drag_annual_pct"] == pytest.approx(0.9)


def test_honest_report_accepts_realistic_costs_and_flags_legacy_bps() -> None:
    ok = build_honest_report(_suite(3.5), commission_cfg=CommissionConfig(), slippage_cfg=SlippageConfig())
    assert ok["cost_model_suspicious"] is False
    legacy = build_honest_report(
        _suite(3.5), commission_cfg=CommissionConfig(), slippage_cfg=SlippageConfig(model="bps", bps=1.0)
    )
    assert legacy["cost_model_suspicious"] is True
    assert "bps" in legacy["cost_model_note"]
    # Without observed data the configured model is priced at a reference order
    est = build_honest_report(_suite(None), commission_cfg=CommissionConfig(), slippage_cfg=SlippageConfig())
    assert est["cost_summary"]["avg_cost_bps_source"] == "model_estimate"
    assert est["cost_summary"]["model_estimate_bps"] > 0.0


def test_honest_report_cost_flag_does_not_change_gates_or_verdict() -> None:
    suite = _suite(0.3, gate_passed=True)
    rep = build_honest_report(suite, commission_cfg=CommissionConfig(), slippage_cfg=SlippageConfig())
    assert rep["cost_model_suspicious"] is True
    assert rep["n_pass"] == 1
    assert rep["verdict"] == "INTERESTING_OWNER_PC_RERUN"
    assert rep["skeptical_flags"] == []
    assert suite["candidates"][0]["gate_passed"] is True


# --------------------------------------------------------------------------- cost ladder


def test_cost_ladder_scales_spread_impact_and_commission() -> None:
    s = AppSettings()
    s.slippage = SlippageConfig(bps=1.0)
    s.commission = CommissionConfig()
    stressed = _with_slippage_mult(s, 3.0)
    assert stressed.slippage.bps == pytest.approx(3.0)
    assert stressed.slippage.spread_bps_default == pytest.approx(3.0 * s.slippage.spread_bps_default)
    assert stressed.slippage.spread_bps_by_symbol["SPY"] == pytest.approx(3.0 * s.slippage.spread_bps_by_symbol["SPY"])
    assert stressed.slippage.impact_y == pytest.approx(3.0 * s.slippage.impact_y)
    assert stressed.commission.per_share == pytest.approx(0.015)
    assert stressed.commission.min_per_order == pytest.approx(3.0)
    assert stressed.commission.max_percent_of_value == pytest.approx(1.0)  # statutory cap untouched
    # Original untouched
    assert s.slippage.bps == 1.0
    assert s.slippage.spread_bps_by_symbol["SPY"] == 0.5
    assert s.commission.min_per_order == 1.0
    # The stressed model is really more expensive end to end
    cheap = total_order_cost("SPY", 100, 100.0, D, commission_cfg=s.commission, slippage_cfg=s.slippage)
    dear = total_order_cost(
        "SPY", 100, 100.0, D, commission_cfg=stressed.commission, slippage_cfg=stressed.slippage
    )
    assert dear.total > cheap.total
