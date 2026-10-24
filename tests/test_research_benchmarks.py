from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Mapping

import numpy as np
import pandas as pd
import pytest

from ibtrader.research.benchmarks import (
    ALL_WEATHER_STATIC,
    all_weather_static,
    load_external_index_csv,
    random_long_only_portfolios,
    rebalanced_portfolio_returns,
    returns_stats,
    sharpe_percentile,
    sixty_forty,
)

SYMBOLS: List[str] = ["SPY", "IEF", "TLT", "GLD", "PDBC"]
VOLS: Dict[str, float] = {"SPY": 0.16, "IEF": 0.06, "TLT": 0.14, "GLD": 0.15, "PDBC": 0.18}
DRIFT: Dict[str, float] = {"SPY": 0.08, "IEF": 0.02, "TLT": 0.03, "GLD": 0.04, "PDBC": 0.0}


def _prices(seed: int = 0, n: int = 520) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    data: Dict[str, np.ndarray] = {}
    for sym in SYMBOLS:
        daily = rng.standard_normal(n) * VOLS[sym] / math.sqrt(252.0) + DRIFT[sym] / 252.0
        data[sym] = 100.0 * np.cumprod(1.0 + daily)
    return pd.DataFrame(data, index=idx)


def _manual_rebalanced(prices: pd.DataFrame, weights: Mapping[str, float], cost_bps: float, freq: str) -> pd.Series:
    """Simulación lenta e independiente (bucle por día) con la misma convención que el módulo."""
    syms = list(weights)
    w = np.array([weights[s] for s in syms], dtype=float)
    w = w / w.sum()
    rets = prices[syms].pct_change(fill_method=None).iloc[1:]
    periods = rets.index.to_period(freq)
    holdings = w.copy()
    prev_total = 1.0
    out: List[float] = []
    n = len(rets)
    for i in range(n):
        holdings = holdings * (1.0 + rets.iloc[i].to_numpy(dtype=float))
        total = float(holdings.sum())
        last_of_period = i < n - 1 and periods[i + 1] != periods[i]
        if last_of_period:
            actual = holdings / total
            turnover = float(np.abs(actual - w).sum())
            total *= 1.0 - turnover * cost_bps * 1e-4
            holdings = w * total
        out.append(total / prev_total - 1.0)
        prev_total = total
    return pd.Series(out, index=rets.index)


def test_sixty_forty_two_identical_assets_reproduces_asset() -> None:
    px = _prices()
    px["IEF"] = px["SPY"]
    r = sixty_forty(px, equity="SPY", bonds="IEF", rebalance="M", cost_bps=5.0)
    expected = px["SPY"].pct_change(fill_method=None).iloc[1:]
    assert np.allclose(r.to_numpy(), expected.to_numpy(), atol=1e-12)
    assert r.name == "60_40"
    assert r.attrs["dropped"] == []


def test_monthly_rebalance_cost_reduces_total_return() -> None:
    px = _prices()
    with_cost = rebalanced_portfolio_returns(px, {"SPY": 0.6, "IEF": 0.4}, rebalance="M", cost_bps=5.0)
    no_cost = rebalanced_portfolio_returns(px, {"SPY": 0.6, "IEF": 0.4}, rebalance="M", cost_bps=0.0)
    assert returns_stats(with_cost)["total_return"] < returns_stats(no_cost)["total_return"]
    assert (with_cost <= no_cost + 1e-15).all()
    assert (with_cost < no_cost).sum() >= 10  # solo los cierres de mes pagan


def test_never_is_buy_and_hold() -> None:
    px = _prices()
    r = rebalanced_portfolio_returns(px, {"SPY": 0.6, "IEF": 0.4}, rebalance="never", cost_bps=5.0)
    value = 0.6 * px["SPY"] / px["SPY"].iloc[0] + 0.4 * px["IEF"] / px["IEF"].iloc[0]
    expected = value.pct_change(fill_method=None).iloc[1:]
    assert np.allclose(r.to_numpy(), expected.to_numpy(), atol=1e-12)


@pytest.mark.parametrize("freq", ["M", "Q"])
def test_rebalanced_matches_independent_loop(freq: str) -> None:
    px = _prices(seed=2)
    weights = {"SPY": 0.3, "TLT": 0.4, "GLD": 0.3}
    fast = rebalanced_portfolio_returns(px, weights, rebalance=freq, cost_bps=7.0)
    slow = _manual_rebalanced(px, weights, cost_bps=7.0, freq=freq)
    assert len(fast) == len(px) - 1
    assert np.allclose(fast.to_numpy(), slow.to_numpy(), atol=1e-12)


def test_dropped_symbols_recorded_and_weights_renormalized() -> None:
    px = _prices()
    r = rebalanced_portfolio_returns(px, {"SPY": 0.5, "IEF": 0.3, "XXX": 0.2}, rebalance="M")
    assert r.attrs["dropped"] == ["XXX"]
    assert r.attrs["weights"]["SPY"] == pytest.approx(0.625)
    assert r.attrs["weights"]["IEF"] == pytest.approx(0.375)
    with pytest.raises(ValueError):
        rebalanced_portfolio_returns(px, {"XXX": 1.0})


def test_invalid_rebalance_raises() -> None:
    with pytest.raises(ValueError):
        rebalanced_portfolio_returns(_prices(), {"SPY": 1.0}, rebalance="banana")


def test_all_weather_static_sums_to_one_and_runs() -> None:
    assert sum(ALL_WEATHER_STATIC.values()) == pytest.approx(1.0)
    assert set(ALL_WEATHER_STATIC) == {"SPY", "TLT", "IEF", "GLD", "PDBC"}
    px = _prices()
    r = all_weather_static(px)
    assert r.name == "all_weather_static"
    assert len(r) == len(px) - 1
    assert np.isfinite(r.to_numpy()).all()
    assert r.attrs["dropped"] == []


def test_random_portfolios_reproducible_and_weights_sum_one() -> None:
    px = _prices()
    a = random_long_only_portfolios(px, n=25, seed=42)
    b = random_long_only_portfolios(px, n=25, seed=42)
    pd.testing.assert_frame_equal(a, b)
    assert a.shape == (len(px) - 1, 25)
    w = a.attrs["weights"]
    assert w.shape == (25, len(SYMBOLS))
    assert np.allclose(w.sum(axis=1).to_numpy(), 1.0)
    assert (w >= 0).all().all()
    assert a.attrs["seed"] == 42
    c = random_long_only_portfolios(px, n=25, seed=43)
    assert not np.allclose(a.to_numpy(), c.to_numpy())


def test_random_portfolio_column_equals_single_portfolio_with_same_weights() -> None:
    px = _prices(seed=5)
    rand = random_long_only_portfolios(px, n=8, seed=1, rebalance="M", cost_bps=5.0)
    w = rand.attrs["weights"].iloc[3].to_dict()
    single = rebalanced_portfolio_returns(px, w, rebalance="M", cost_bps=5.0)
    assert np.allclose(rand.iloc[:, 3].to_numpy(), single.to_numpy(), atol=1e-12)


def test_sharpe_percentile_bounds() -> None:
    sharpes = [0.0, 1.0, 2.0, 3.0]
    assert sharpe_percentile(-1.0, sharpes) == 0.0
    assert sharpe_percentile(2.0, sharpes) == 50.0
    assert sharpe_percentile(10.0, sharpes) == 100.0
    assert math.isnan(sharpe_percentile(1.0, []))


def test_returns_stats_constant_series() -> None:
    r = pd.Series(0.001, index=pd.bdate_range("2024-01-01", periods=252))
    st = returns_stats(r)
    total = 1.001**252 - 1.0
    assert st["total_return"] == pytest.approx(total)
    assert st["cagr"] == pytest.approx(total)
    assert st["vol"] == 0.0
    assert math.isnan(st["sharpe"])
    assert st["max_dd"] == 0.0
    assert st["n_days"] == 252


def test_returns_stats_known_drawdown_and_sharpe() -> None:
    r = pd.Series([0.1, -0.5, 0.2])
    st = returns_stats(r)
    assert st["max_dd"] == pytest.approx(-0.5)
    assert st["total_return"] == pytest.approx(1.1 * 0.5 * 1.2 - 1.0)
    assert st["sharpe"] == pytest.approx(r.mean() / r.std(ddof=0) * math.sqrt(252.0))
    assert st["vol"] == pytest.approx(r.std(ddof=0) * math.sqrt(252.0))
    empty = returns_stats(pd.Series(dtype=float))
    assert empty["n_days"] == 0 and math.isnan(empty["sharpe"])


def test_load_external_index_csv(tmp_path: Path) -> None:
    csv = tmp_path / "sg_trend.csv"
    rows = ["Date,Index Level", "2024-01-03,102", "2024-01-02,101", "2024-01-01,100", "2024-01-03,103"]
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    r = load_external_index_csv(str(csv))
    assert r.name == "sg_trend"
    assert list(r.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert r.iloc[0] == pytest.approx(0.01)
    assert r.iloc[1] == pytest.approx(103.0 / 101.0 - 1.0)  # duplicado: gana el último
    assert r.attrs["source"] == str(csv)
    with pytest.raises(FileNotFoundError):
        load_external_index_csv(str(tmp_path / "missing.csv"))
