"""Pure transaction-cost functions for US stocks/ETFs at Interactive Brokers.

Every function here is stateless and deterministic: same inputs, same output.
Parameters live in :mod:`ibtrader.config` (``CommissionConfig``,
``RegFeesConfig``, ``SlippageConfig``); defaults were read on 2026-10-21 from
IBKR's public pricing pages and the research annex
``docs/research/quant-funds-2026-10-21/04-ejecucion-costos-ibkr.md``.
Formulas, worked examples and the sanity rules are documented in
``COST_MODEL.md`` at the repository root.

Sign convention: ``shares > 0`` is a buy, ``shares < 0`` is a sell. Costs are
always returned as non-negative USD amounts.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Set, Tuple

import pandas as pd

from ..config import CommissionConfig, RegFeesConfig, SlippageConfig

log = logging.getLogger("ibtrader.execution.costs")

DateLike = Any  # str | date | datetime | pd.Timestamp


def _qty(shares: int) -> int:
    return abs(int(shares))


def _finite_positive(x: Optional[float]) -> bool:
    if x is None:
        return False
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(xf) and xf > 0.0


def _finite(x: Optional[float]) -> bool:
    if x is None:
        return False
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------- commission


def commission(cfg: CommissionConfig, shares: int, price: float) -> float:
    """IBKR commission for one order in USD.

    Fixed (default):
        ``min(max(min_per_order, per_share*|shares|) + percent_of_value/100*notional,
        max_percent_of_value/100*notional)``.  ``max_percent_of_value <= 0`` disables the cap.
    Tiered:
        ``max(tiered_min_per_order, tiered_per_share*|shares|)
        + (tiered_exchange_per_share + clearing_per_share)*|shares|
        + pass_through_pct_of_commission * broker_commission``.
    Orders of zero shares or non-positive price cost nothing.
    """
    qty = _qty(shares)
    px = float(price)
    if qty == 0 or not _finite_positive(px):
        return 0.0
    notional = qty * px
    if cfg.model == "tiered":
        broker = max(float(cfg.tiered_min_per_order), float(cfg.tiered_per_share) * qty)
        venue = (float(cfg.tiered_exchange_per_share) + float(cfg.clearing_per_share)) * qty
        pass_through = float(cfg.pass_through_pct_of_commission) * broker
        return float(broker + venue + pass_through)
    base = max(float(cfg.min_per_order), float(cfg.per_share) * qty)
    base += float(cfg.percent_of_value) / 100.0 * notional
    cap_pct = float(cfg.max_percent_of_value)
    if cap_pct > 0.0:
        base = min(base, cap_pct / 100.0 * notional)
    return float(base)


# --------------------------------------------------------------------------- regulatory fees


def _as_timestamp(value: DateLike) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if ts is pd.NaT:
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None) if ts.tz is not None else ts.tz_localize(None)
    return ts.normalize()


def taf_paused(cfg: RegFeesConfig, trade_date: DateLike) -> bool:
    """True when FINRA TAF is USD 0 on ``trade_date`` (``trade_date <= finra_taf_paused_until``)."""
    until = _as_timestamp(cfg.finra_taf_paused_until) if cfg.finra_taf_paused_until else None
    if until is None:
        return False
    td = _as_timestamp(trade_date)
    if td is None:
        # Unknown date: assume the pause does not apply (conservative = charge the fee)
        return False
    return bool(td <= until)


def reg_fees(
    cfg: RegFeesConfig,
    shares: int,
    price: float,
    trade_date: DateLike,
    is_sell: bool,
) -> float:
    """US regulatory fees in USD. Charged on sells only (SEC Section 31 + FINRA TAF + CAT)."""
    if not is_sell:
        return 0.0
    qty = _qty(shares)
    px = float(price)
    if qty == 0 or not _finite_positive(px):
        return 0.0
    notional = qty * px
    sec = float(cfg.sec_fee_rate) * notional
    taf = 0.0
    if not taf_paused(cfg, trade_date):
        taf = min(float(cfg.finra_taf_per_share) * qty, float(cfg.finra_taf_max_per_order))
    cat = float(cfg.cat_per_share) * qty
    return float(sec + taf + cat)


# --------------------------------------------------------------------------- spread


def spread_bps(cfg: SlippageConfig, symbol: str) -> float:
    """Full quoted spread in bps for ``symbol`` (per-symbol table, else default)."""
    table = cfg.spread_bps_by_symbol or {}
    try:
        return float(table.get(symbol, cfg.spread_bps_default))
    except (TypeError, ValueError):
        return float(cfg.spread_bps_default)


def half_spread_fraction(cfg: SlippageConfig, symbol: str) -> float:
    """Half-spread as a fraction of price: ``half_spread_mult * 0.5 * spread_bps / 1e4``."""
    return float(cfg.half_spread_mult) * 0.5 * spread_bps(cfg, symbol) / 1e4


def half_spread(cfg: SlippageConfig, symbol: str, shares: int, price: float) -> float:
    """Half-spread cost in USD for crossing the spread on ``|shares|`` at ``price``."""
    qty = _qty(shares)
    px = float(price)
    if qty == 0 or not _finite_positive(px):
        return 0.0
    return float(half_spread_fraction(cfg, symbol) * qty * px)


# --------------------------------------------------------------------------- impact


def impact_fraction(
    cfg: SlippageConfig,
    shares: int,
    sigma_daily: Optional[float],
    adv_shares: Optional[float],
) -> float:
    """Square-root impact as a fraction of price: ``Y * sigma * (|shares|/ADV)^exponent``.

    Returns 0 when ``sigma_daily`` or ``adv_shares`` are missing / non-finite / ADV <= 0.
    """
    qty = _qty(shares)
    if qty == 0:
        return 0.0
    if not _finite(sigma_daily) or not _finite_positive(adv_shares):
        return 0.0
    sigma = max(float(sigma_daily), 0.0)  # type: ignore[arg-type]
    if sigma == 0.0:
        return 0.0
    participation = qty / float(adv_shares)  # type: ignore[arg-type]
    scaled = math.pow(participation, float(cfg.impact_exponent))
    return float(float(cfg.impact_y) * sigma * scaled)


def impact(
    cfg: SlippageConfig,
    shares: int,
    price: float,
    sigma_daily: Optional[float],
    adv_shares: Optional[float],
) -> float:
    """Impact cost in USD: ``impact_fraction * |shares| * price``; 0 without ADV / sigma."""
    qty = _qty(shares)
    px = float(price)
    if qty == 0 or not _finite_positive(px):
        return 0.0
    return float(impact_fraction(cfg, shares, sigma_daily, adv_shares) * qty * px)


def impact_inputs_available(sigma_daily: Optional[float], adv_shares: Optional[float]) -> bool:
    return _finite(sigma_daily) and _finite_positive(adv_shares)


def warn_missing_impact_inputs(symbol: str, warned: Optional[Set[str]]) -> None:
    """Log once per symbol (per ``warned`` set) that impact is being modelled as 0."""
    if warned is None:
        return
    if symbol in warned:
        return
    warned.add(symbol)
    log.info("impact_inputs_missing sym=%s impact=0 (no ADV/sigma yet; warm-up or no volume)", symbol)


# --------------------------------------------------------------------------- legacy slippage


def slippage_legacy_bps(cfg: SlippageConfig, price: float, side: int) -> float:
    """Legacy flat-bps fill price (``model == "bps"``): ``price * (1 + bps/1e4 * side)``."""
    bps = float(cfg.bps) / 10000.0
    return float(price) * (1.0 + bps * (1 if side >= 0 else -1))


def estimated_fill_price(cfg: SlippageConfig, symbol: str, price: float, side: int) -> float:
    """Fill estimate used for sizing (no impact term, which needs the quantity)."""
    if cfg.model == "bps":
        return slippage_legacy_bps(cfg, price, side)
    sgn = 1 if side >= 0 else -1
    return float(price) * (1.0 + sgn * half_spread_fraction(cfg, symbol))


# --------------------------------------------------------------------------- all-in order cost


@dataclass(frozen=True)
class OrderCost:
    """All-in cost of one order. ``notional`` is ``|shares| * fill_price``."""

    symbol: str
    shares: int
    reference_price: float
    fill_price: float
    commission: float
    reg_fees: float
    half_spread: float
    impact: float
    notional: float = field(default=0.0)
    total: float = field(default=0.0)
    bps_all_in: float = field(default=0.0)

    def __post_init__(self) -> None:
        notional = abs(int(self.shares)) * float(self.fill_price)
        total = float(self.commission + self.reg_fees + self.half_spread + self.impact)
        bps = (total / notional * 1e4) if notional > 0 else 0.0
        object.__setattr__(self, "notional", float(notional))
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "bps_all_in", float(bps))

    @property
    def explicit_fees(self) -> float:
        """Cash fees charged on top of the fill (commission + regulatory)."""
        return float(self.commission + self.reg_fees)


def total_order_cost(
    symbol: str,
    shares: int,
    price: float,
    trade_date: DateLike,
    *,
    commission_cfg: CommissionConfig,
    slippage_cfg: SlippageConfig,
    reg_fees_cfg: Optional[RegFeesConfig] = None,
    sigma_daily: Optional[float] = None,
    adv_shares: Optional[float] = None,
    warned: Optional[Set[str]] = None,
) -> OrderCost:
    """Combine spread, impact, commission and regulatory fees for one order.

    ``slippage_cfg.model == "bps"`` reproduces the legacy engine exactly: the fill is
    ``price * (1 + bps/1e4 * side)`` and the flat slippage is reported as ``half_spread``.
    ``"spread_impact"`` fills at ``price * (1 + side * (half_spread_frac + impact_frac))``.
    Commission is charged on the fill notional; regulatory fees only on sells.
    """
    qty = _qty(shares)
    px = float(price)
    side = 1 if int(shares) >= 0 else -1
    rf_cfg = reg_fees_cfg if reg_fees_cfg is not None else RegFeesConfig()
    if qty == 0 or not _finite_positive(px):
        return OrderCost(symbol, int(shares), px, px, 0.0, 0.0, 0.0, 0.0)
    if slippage_cfg.model == "bps":
        fill = slippage_legacy_bps(slippage_cfg, px, side)
        hs_cost = qty * px * float(slippage_cfg.bps) / 10000.0
        imp_cost = 0.0
    else:
        hs_frac = half_spread_fraction(slippage_cfg, symbol)
        if impact_inputs_available(sigma_daily, adv_shares):
            imp_frac = impact_fraction(slippage_cfg, qty, sigma_daily, adv_shares)
        else:
            imp_frac = 0.0
            warn_missing_impact_inputs(symbol, warned)
        fill = px * (1.0 + side * (hs_frac + imp_frac))
        hs_cost = hs_frac * qty * px
        imp_cost = imp_frac * qty * px
    comm = commission(commission_cfg, qty, fill)
    fees = reg_fees(rf_cfg, qty, fill, trade_date, is_sell=side < 0)
    return OrderCost(
        symbol=symbol,
        shares=int(shares),
        reference_price=px,
        fill_price=float(fill),
        commission=float(comm),
        reg_fees=float(fees),
        half_spread=float(hs_cost),
        impact=float(imp_cost),
    )


# --------------------------------------------------------------------------- rolling inputs


def rolling_adv_and_sigma(
    df: pd.DataFrame,
    adv_window: int,
    sigma_window: int,
) -> Tuple[pd.Series, pd.Series]:
    """Rolling ADV (shares) and daily sigma of close-to-close returns, shifted one bar.

    The value at bar ``t`` only uses bars ``<= t-1`` (no look at the current bar).
    Both series are NaN during warm-up (fewer than ``window`` prior bars) and ADV is
    all-NaN when the frame has no ``volume`` column.
    """
    adv_w = max(int(adv_window), 1)
    sig_w = max(int(sigma_window), 2)
    index = df.index
    if "volume" in df.columns:
        vol = pd.to_numeric(df["volume"], errors="coerce").astype(float)
        adv = vol.rolling(adv_w, min_periods=adv_w).mean().shift(1)
    else:
        adv = pd.Series(float("nan"), index=index, dtype=float)
    if "close" in df.columns:
        close = pd.to_numeric(df["close"], errors="coerce").astype(float)
        rets = close.pct_change()
        sigma = rets.rolling(sig_w, min_periods=sig_w).std(ddof=0).shift(1)
    else:
        sigma = pd.Series(float("nan"), index=index, dtype=float)
    adv.name = "adv_shares"
    sigma.name = "sigma_daily"
    return adv.astype(float), sigma.astype(float)


def model_all_in_bps(
    symbol: str,
    order_usd: float,
    price: float,
    *,
    commission_cfg: CommissionConfig,
    slippage_cfg: SlippageConfig,
    reg_fees_cfg: Optional[RegFeesConfig] = None,
    trade_date: DateLike = None,
    sigma_daily: Optional[float] = None,
    adv_shares: Optional[float] = None,
) -> float:
    """Theoretical all-in cost (bps of notional) of a round trip averaged per order.

    Buys pay commission + spread + impact; sells also pay regulatory fees, so the
    per-order figure is the mean of the two legs. Used by reports to sanity-check a
    configured model against IBKR's observed 2.5-4 bp (jul-2026).
    """
    px = float(price)
    if not _finite_positive(px) or not _finite_positive(order_usd):
        return 0.0
    qty = max(int(float(order_usd) // px), 1)
    td = trade_date if trade_date is not None else date.today()
    if isinstance(td, datetime):
        td = td.date()
    buy = total_order_cost(
        symbol, qty, px, td, commission_cfg=commission_cfg, slippage_cfg=slippage_cfg,
        reg_fees_cfg=reg_fees_cfg, sigma_daily=sigma_daily, adv_shares=adv_shares,
    )
    sell = total_order_cost(
        symbol, -qty, px, td, commission_cfg=commission_cfg, slippage_cfg=slippage_cfg,
        reg_fees_cfg=reg_fees_cfg, sigma_daily=sigma_daily, adv_shares=adv_shares,
    )
    return float((buy.bps_all_in + sell.bps_all_in) / 2.0)


__all__ = [
    "OrderCost",
    "commission",
    "estimated_fill_price",
    "half_spread",
    "half_spread_fraction",
    "impact",
    "impact_fraction",
    "model_all_in_bps",
    "reg_fees",
    "rolling_adv_and_sigma",
    "slippage_legacy_bps",
    "spread_bps",
    "taf_paused",
    "total_order_cost",
    "warn_missing_impact_inputs",
]
