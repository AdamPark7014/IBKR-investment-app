"""Stage graph of the phase-2 system (pysystemtrade-style), point-in-time end to end.

``run_system`` chains the stages written by ``pipeline/*`` and ``portfolio/*``::

    prices ─► vol ─► rules (raw forecasts) ─► scale/cap (pooled per rule)
           ─► FDM + combine (per symbol) ─► vol scalar ─► subsystem position
           ─► instrument weights (box risk parity | HRP | equal) ─► IDM
           ─► portfolio positions ─► buffering ─► target weights

Every stage is point-in-time: the value at ``t`` only uses bars ``<= t``. The
pooled forecast scalar (``estimate`` mode) uses the cross-section of the same
day across symbols and is **not** back-filled: before ``scalar_min_periods``
bars it is NaN, the scaled forecasts are NaN and ``warmup_end`` cannot fall
before the first valid scalar (pysystemtrade back-fills; that leaks up to
``scalar_min_periods`` bars of future data into the evaluated window).

Instrument weights are **risk** allocations: the subsystem positions are
already vol-normalised (``vol_scalar ∝ τ/σ``), so box weights are the box risk
budget split equally inside the box (no ``1/σ``) and HRP runs on vol-normalised
returns (``r_t / σ_{t-1}``). Dividing by the volatility again would make each
instrument's risk ∝ ``1/σ``.

No global state: everything the stages need travels in ``SystemConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from ..logging import setup_logging
from ..portfolio.boxes import rolling_box_risk_weights
from ..portfolio.hrp import rolling_hrp_weights
from ..portfolio.multiplier import rolling_idm
from .buffering import apply_buffer, position_buffer
from .combine import combine_forecasts, equal_weights, forecast_div_multiplier
from .forecast import estimate_forecast_scalar, scale_and_cap
from .portfolio_stage import average_abs_positions, portfolio_positions, positions_to_weights
from .rules import DEFAULT_RULES, FIXED_FORECAST_SCALARS, run_rules
from .sizing import subsystem_position, vol_scalar
from .vol import pct_vol_daily, price_vol_daily

log = setup_logging()

InstrumentWeighting = Literal["box_risk_parity", "hrp", "equal"]

#: Old name of ``box_risk_parity`` (it divided the vol-normalised subsystems by σ a second time).
#: Still accepted so saved configs load, but it now means ``box_risk_parity``.
LEGACY_WEIGHTING_ALIASES: Dict[str, str] = {"box_inverse_vol": "box_risk_parity"}
ForecastScalarMode = Literal["estimate", "fixed"]

#: Target absolute forecast after scaling (pysystemtrade convention: |f| averages 10).
TARGET_ABS_FORECAST = 10.0


@dataclass(frozen=True)
class SystemConfig:
    """Everything ``run_system`` needs. Defaults are the pysystemtrade ones adapted to ETFs.

    * ``rules``: trading rules evaluated per symbol (names known to ``pipeline.rules``).
    * ``rule_weights``: forecast weights per rule (``None`` = equal). Keys must match ``rules``.
    * ``forecast_cap``: scaled and combined forecasts are capped at ``±forecast_cap``.
    * ``forecast_scalar_mode``: ``estimate`` = pooled expanding estimate across symbols
      (NaN until ``scalar_min_periods`` bars, never back-filled); ``fixed`` = ``FIXED_FORECAST_SCALARS``
      (rules without a fixed scalar fall back to ``estimate`` and are reported in
      ``SystemOutput.scalar_source``).
    * ``tau``: annual volatility target as a fraction of ``capital``.
    * ``instrument_weighting``: ``box_risk_parity`` (equal risk per box, equal inside the box),
      ``hrp`` (on vol-normalised returns) or ``equal``. ``box_inverse_vol`` is a legacy alias.
    * ``boxes``: symbol → box; a symbol missing from the mapping is its own box.
    * ``long_only`` / ``short_only`` / ``max_leverage``: enforced on the portfolio positions and
      again on the final target weights (the engine caps gross exposure at ``max_total_exposure_pct``).
      ``long_only`` and ``short_only`` are exclusive; both False = long/short.
    * ``tau`` vs ``max_leverage``: ``tau`` is the volatility the system *asks for*; with
      ``max_leverage = 1.0`` (cash account, no margin) a diversified ETF book with bonds cannot
      reach 10 %: the cap binds most days and the realised volatility ends up around 4–6 %. That
      lower figure is the effective target. ``SystemOutput.leverage_capped`` / ``gross_before_cap``
      show how often the cap binds; raising ``max_leverage`` (e.g. 1.5×, margin account) is Adam's
      decision, never a default.
    * ``buffer_frac``: no-trade band around the target as a fraction of the average absolute
      position (``position_buffer``); trades go to the edge of the band.
    """

    rules: Tuple[str, ...] = tuple(DEFAULT_RULES)
    rule_weights: Optional[Dict[str, float]] = None
    forecast_cap: float = 20.0
    forecast_scalar_mode: ForecastScalarMode = "estimate"
    scalar_min_periods: int = 500
    fdm_max: float = 2.5
    tau: float = 0.10
    capital: float = 100_000.0
    instrument_weighting: InstrumentWeighting = "box_risk_parity"
    idm_max: float = 2.5
    buffer_frac: float = 0.10
    long_only: bool = True
    #: Gross exposure cap (fraction of capital). 1.0 = no leverage: see the ``tau`` note above.
    max_leverage: float = 1.0
    boxes: Optional[Dict[str, str]] = None
    short_only: bool = False
    # Secondary knobs (pysystemtrade defaults); exposed so research can shorten warm-ups.
    vol_span: int = 35
    fdm_min_periods: int = 250
    fdm_ewma_span: int = 125
    idm_min_periods: int = 250
    idm_ewma_span: int = 125
    box_lookback: int = 252
    box_min_periods: int = 126
    hrp_lookback: int = 504
    hrp_min_periods: int = 252
    step: int = 21

    def __post_init__(self) -> None:
        legacy = LEGACY_WEIGHTING_ALIASES.get(str(self.instrument_weighting))
        if legacy is not None:
            log.warning("SystemConfig: instrument_weighting %r is now %r", self.instrument_weighting, legacy)
            object.__setattr__(self, "instrument_weighting", legacy)
        if self.instrument_weighting not in ("box_risk_parity", "hrp", "equal"):
            raise ValueError(f"SystemConfig.instrument_weighting unknown: {self.instrument_weighting!r}")
        if not self.rules:
            raise ValueError("SystemConfig.rules must not be empty")
        if len(set(self.rules)) != len(self.rules):
            raise ValueError(f"SystemConfig.rules has duplicates: {self.rules}")
        if self.rule_weights is not None:
            missing = set(self.rules) - set(self.rule_weights)
            extra = set(self.rule_weights) - set(self.rules)
            if missing or extra:
                raise ValueError(
                    "SystemConfig.rule_weights keys must match rules "
                    f"(missing={sorted(missing)}, extra={sorted(extra)})"
                )
            if any(float(w) < 0.0 for w in self.rule_weights.values()):
                raise ValueError("SystemConfig.rule_weights must be non-negative")
        if self.forecast_cap <= 0.0:
            raise ValueError("SystemConfig.forecast_cap must be > 0")
        if self.tau <= 0.0:
            raise ValueError("SystemConfig.tau must be > 0")
        if self.capital <= 0.0:
            raise ValueError("SystemConfig.capital must be > 0")
        if self.buffer_frac < 0.0:
            raise ValueError("SystemConfig.buffer_frac must be >= 0")
        if self.max_leverage <= 0.0:
            raise ValueError("SystemConfig.max_leverage must be > 0")
        if self.long_only and self.short_only:
            raise ValueError("SystemConfig.long_only and short_only are exclusive")
        if self.fdm_max < 1.0 or self.idm_max < 1.0:
            raise ValueError("SystemConfig.fdm_max / idm_max must be >= 1")
        if self.step < 1 or self.scalar_min_periods < 1:
            raise ValueError("SystemConfig.step and scalar_min_periods must be >= 1")

    def forecast_weights(self) -> Dict[str, float]:
        """Forecast weights per rule (equal when ``rule_weights`` is None)."""
        if self.rule_weights is None:
            return dict(equal_weights(list(self.rules)))
        return {r: float(self.rule_weights[r]) for r in self.rules}


@dataclass
class SystemOutput:
    """Every stage of ``run_system`` as DataFrames (dates × symbols) or per-rule mappings.

    * ``raw_forecasts`` / ``scaled_forecasts``: rule → DataFrame (dates × symbols).
    * ``forecast_scalars``: rule → pooled scalar Series (dates); constant in ``fixed`` mode.
    * ``fdm``: DataFrame (dates × symbols) — the FDM is estimated **per symbol** over its
      own rule forecasts (one Series per symbol, assembled as columns).
    * ``idm``: Series (dates) — one multiplier for the whole portfolio.
    * ``subsystem_returns``: ``subsystem_positions.shift(1) · Δprice / capital`` (fraction of
      capital) — what the IDM is estimated on.
    * ``mtm_weights``: ``buffered_positions · price / capital`` every day (diagnostic).
    * ``target_weights``: what the engine consumes — ``mtm_weights`` sampled on the days the
      buffered position changes and held constant in between, so a fixed share count does
      not look like a daily weight change (and does not trade on price drift); sign-clipped
      for ``long_only`` / ``short_only``. When a change pushes gross above ``max_leverage``
      only the symbols that changed that day are scaled down: a symbol whose position did not
      move keeps exactly its weight (rescaling it would be a trade without a signal).
    * ``gross_before_cap`` / ``leverage_capped``: gross exposure of the portfolio positions
      before the ``max_leverage`` cap and whether the cap bound that day.
    * ``warmup_end``: first date on which every stage has a value for ≥ 2 symbols (``None``
      when that never happens).
    * ``scalar_source``: rule → ``"estimate"`` | ``"fixed"`` (what was actually used).
    """

    prices: pd.DataFrame
    vol_price: pd.DataFrame
    pct_vol: pd.DataFrame
    raw_forecasts: Dict[str, pd.DataFrame]
    scaled_forecasts: Dict[str, pd.DataFrame]
    forecast_scalars: Dict[str, pd.Series]
    fdm: pd.DataFrame
    combined_forecast: pd.DataFrame
    vol_scalar: pd.DataFrame
    subsystem_positions: pd.DataFrame
    instrument_weights: pd.DataFrame
    idm: pd.Series
    positions: pd.DataFrame
    buffered_positions: pd.DataFrame
    target_weights: pd.DataFrame
    warmup_end: Optional[pd.Timestamp]
    subsystem_returns: pd.DataFrame = field(default_factory=pd.DataFrame)
    mtm_weights: pd.DataFrame = field(default_factory=pd.DataFrame)
    gross_before_cap: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    leverage_capped: pd.Series = field(default_factory=lambda: pd.Series(dtype=bool))
    scalar_source: Dict[str, str] = field(default_factory=dict)
    config: Optional[SystemConfig] = None


# --------------------------------------------------------------------------- helpers


def _clean_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.shape[1] == 0:
        raise ValueError("run_system: prices must be a non-empty DataFrame (dates × symbols)")
    px = prices.astype(float).copy()
    px.index = pd.DatetimeIndex(px.index)
    if px.index.has_duplicates:
        raise ValueError("run_system: prices index has duplicated dates")
    px = px.sort_index()
    empty = [c for c in px.columns if px[c].notna().sum() == 0]
    if empty:
        log.warning("run_system: dropping symbols without prices: %s", empty)
        px = px.drop(columns=empty)
    if px.shape[1] == 0:
        raise ValueError("run_system: no symbol has any price")
    px.columns = [str(c) for c in px.columns]
    return px


def _frame(index: pd.Index, columns: List[str], series_by_symbol: Mapping[str, pd.Series]) -> pd.DataFrame:
    """Assemble per-symbol Series into a (dates × symbols) frame on ``index`` (missing → NaN)."""
    out = pd.DataFrame(index=index, columns=columns, dtype=float)
    for sym in columns:
        s = series_by_symbol.get(sym)
        if s is None:
            continue
        out[sym] = pd.Series(s, dtype=float).reindex(index)
    return out


def _as_series(value: object, index: pd.Index, name: str) -> pd.Series:
    """Coerce a stage output (Series, scalar or array) to a float Series on ``index``."""
    if isinstance(value, pd.Series):
        return value.astype(float).reindex(index)
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise TypeError(f"{name}: expected a Series, got a DataFrame with {value.shape[1]} columns")
        return value.iloc[:, 0].astype(float).reindex(index)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return pd.Series(float(value), index=index)
    arr = np.asarray(value, dtype=float)
    if arr.shape != (len(index),):
        raise TypeError(f"{name}: cannot align an array of shape {arr.shape} with {len(index)} dates")
    return pd.Series(arr, index=index)


def _forecast_scalar(
    rule: str, raw: pd.DataFrame, cfg: SystemConfig
) -> Tuple[pd.Series, str]:
    """Pooled scalar Series for ``rule`` and the source actually used (``estimate`` | ``fixed``)."""
    index = raw.index
    if cfg.forecast_scalar_mode == "fixed":
        fixed = FIXED_FORECAST_SCALARS.get(rule)
        if fixed is not None:
            return pd.Series(float(fixed), index=index, name=rule), "fixed"
        log.warning("run_system: no fixed forecast scalar for rule %s; estimating it instead", rule)
    pooled = {sym: raw[sym].dropna() for sym in raw.columns if raw[sym].notna().any()}
    if not pooled:
        return pd.Series(np.nan, index=index, name=rule), "estimate"
    # No backfill: a back-filled scalar is estimated with up to ``scalar_min_periods`` future bars.
    est = estimate_forecast_scalar(
        pooled,
        target_abs=TARGET_ABS_FORECAST,
        min_periods=cfg.scalar_min_periods,
        backfill=False,
    )
    scalar = _as_series(est, index, f"estimate_forecast_scalar[{rule}]").ffill()
    scalar.name = rule
    return scalar, "estimate"


def _equal_instrument_weights(px: pd.DataFrame) -> pd.DataFrame:
    has = px.notna()
    n = has.sum(axis=1).astype(float).replace(0.0, np.nan)
    return has.astype(float).div(n, axis=0)


def _instrument_weights(px: pd.DataFrame, pct_vol: pd.DataFrame, cfg: SystemConfig) -> pd.DataFrame:
    """Risk weights per instrument for vol-normalised subsystems (see the module docstring)."""
    returns = px.pct_change()
    if cfg.instrument_weighting == "equal":
        w = _equal_instrument_weights(px)
    elif cfg.instrument_weighting == "hrp":
        # Yesterday's vol only (point-in-time): r_t / σ_{t-1} has ~unit variance for every symbol,
        # so HRP allocates on correlations instead of dividing by σ a second time.
        norm = returns.div(pct_vol.reindex(index=px.index, columns=px.columns).shift(1))
        norm = norm.replace([np.inf, -np.inf], np.nan)
        w = rolling_hrp_weights(
            norm,
            lookback=cfg.hrp_lookback,
            min_periods=cfg.hrp_min_periods,
            step=cfg.step,
        )
    elif cfg.instrument_weighting == "box_risk_parity":
        boxes = {sym: (cfg.boxes or {}).get(sym, sym) for sym in px.columns}
        w = rolling_box_risk_weights(
            returns,
            boxes,
            lookback=cfg.box_lookback,
            min_periods=cfg.box_min_periods,
            step=cfg.step,
        )
    else:  # pragma: no cover - Literal guards this
        raise ValueError(f"unknown instrument_weighting {cfg.instrument_weighting!r}")
    w = pd.DataFrame(w, dtype=float).reindex(index=px.index)
    return w.reindex(columns=list(px.columns))


def _capped_piecewise_weights(buffered: pd.DataFrame, mtm: pd.DataFrame, cfg: SystemConfig) -> pd.DataFrame:
    """Engine target weights: ``mtm`` sampled where each symbol's buffered position changes.

    Held constant in between (a fixed share count must not look like a weight change), sign-clipped
    for ``long_only`` / ``short_only`` and capped at ``max_leverage`` by scaling down **only the
    symbols that changed that day**. The unchanged ones keep their exact weight, so the engine never
    trades a symbol whose position did not move. Gross can only rise on a change day (held weights
    are constants), and the unchanged part already fitted under the cap the day before, so scaling
    the changed part is always enough.
    """
    cols = list(buffered.columns)
    b = buffered.reindex(columns=cols).to_numpy(dtype=float)
    w = mtm.reindex(index=buffered.index, columns=cols).to_numpy(dtype=float)
    prev = np.vstack([np.full((1, len(cols)), np.nan), b[:-1]])
    valid = ~np.isnan(b)
    changed = valid & (np.isnan(prev) | (b != prev))
    if cfg.long_only:
        w = np.where(np.isnan(w), w, np.maximum(w, 0.0))
    if cfg.short_only:
        w = np.where(np.isnan(w), w, np.minimum(w, 0.0))
    cap = float(cfg.max_leverage)
    w = np.clip(w, -cap, cap)
    out = np.full_like(w, np.nan)
    held = np.full(len(cols), np.nan)
    for i in range(w.shape[0]):
        row = held.copy()
        # A change on a bar without a price keeps the last sampled weight (as a forward-fill would).
        ch = changed[i] & ~np.isnan(w[i])
        row[ch] = w[i, ch]
        row[~valid[i]] = np.nan
        gross = float(np.nansum(np.abs(row)))
        if gross > cap * (1.0 + 1e-12):
            moved = ch & valid[i]
            fixed_gross = float(np.nansum(np.abs(row[valid[i] & ~ch])))
            moved_gross = float(np.nansum(np.abs(row[moved])))
            if moved_gross > 0.0 and fixed_gross <= cap:
                row[moved] *= max(cap - fixed_gross, 0.0) / moved_gross
            else:  # cannot happen from a capped state; keep the cap anyway
                row[valid[i]] *= cap / gross
        out[i] = row
        held = row
    return pd.DataFrame(out, index=buffered.index, columns=cols, dtype=float)


def _warmup_end(stage_validity: List[pd.DataFrame], idm: pd.Series, min_symbols: int = 2) -> Optional[pd.Timestamp]:
    if not stage_validity:
        return None
    valid = stage_validity[0].copy()
    for frame in stage_validity[1:]:
        valid &= frame.reindex(index=valid.index, columns=valid.columns).fillna(False).astype(bool)
    valid = valid.mul(idm.reindex(valid.index).notna(), axis=0)
    n_ok = valid.sum(axis=1)
    hits = n_ok[n_ok >= min_symbols]
    if hits.empty:
        return None
    return pd.Timestamp(hits.index[0])


# --------------------------------------------------------------------------- the system


def run_system(prices: pd.DataFrame, cfg: SystemConfig) -> SystemOutput:
    """Run every stage over ``prices`` (dates × symbols, close) and return them all.

    See the module docstring for the chain and ``SystemOutput`` for what each field
    holds. Symbols with no prices at all are dropped (logged); symbols that list late
    simply carry NaN until their stages warm up.
    """
    px = _clean_prices(prices)
    index = px.index
    symbols = list(px.columns)
    series_px = {sym: px[sym].dropna() for sym in symbols}

    # 1. Volatility (price units for the rules, fraction for sizing).
    vol_price = _frame(
        index, symbols, {sym: _as_series(price_vol_daily(s, span=cfg.vol_span), s.index, "price_vol_daily")
                         for sym, s in series_px.items()}
    )
    pct_vol = _frame(
        index, symbols, {sym: _as_series(pct_vol_daily(s, span=cfg.vol_span), s.index, "pct_vol_daily")
                         for sym, s in series_px.items()}
    )

    # 2. Raw forecasts per rule and symbol.
    raw_by_rule = run_rules(
        series_px,
        {sym: vol_price[sym].reindex(s.index) for sym, s in series_px.items()},
        list(cfg.rules),
    )
    raw_forecasts: Dict[str, pd.DataFrame] = {}
    for rule in cfg.rules:
        per_symbol = raw_by_rule.get(rule) or {}
        raw_forecasts[rule] = _frame(
            index, symbols, {sym: _as_series(v, index, f"run_rules[{rule}][{sym}]") for sym, v in per_symbol.items()}
        )

    # 3. Scaling pooled per rule across symbols, then cap.
    forecast_scalars: Dict[str, pd.Series] = {}
    scaled_forecasts: Dict[str, pd.DataFrame] = {}
    scalar_source: Dict[str, str] = {}
    for rule in cfg.rules:
        scalar, source = _forecast_scalar(rule, raw_forecasts[rule], cfg)
        forecast_scalars[rule] = scalar
        scalar_source[rule] = source
        scaled_forecasts[rule] = _frame(
            index,
            symbols,
            {
                sym: _as_series(
                    scale_and_cap(raw_forecasts[rule][sym], scalar, cap=cfg.forecast_cap),
                    index,
                    f"scale_and_cap[{rule}]",
                )
                for sym in symbols
            },
        )

    # 4. FDM per symbol over its rules, then combination.
    weights = cfg.forecast_weights()
    fdm_by_symbol: Dict[str, pd.Series] = {}
    combined_by_symbol: Dict[str, pd.Series] = {}
    for sym in symbols:
        fc = pd.DataFrame({rule: scaled_forecasts[rule][sym] for rule in cfg.rules}, index=index)
        fdm_s = _as_series(
            forecast_div_multiplier(
                fc,
                weights,
                corr_floor=0.0,
                dm_max=cfg.fdm_max,
                min_periods=cfg.fdm_min_periods,
                ewma_span=cfg.fdm_ewma_span,
                step=cfg.step,
            ),
            index,
            f"forecast_div_multiplier[{sym}]",
        )
        fdm_by_symbol[sym] = fdm_s
        combined_by_symbol[sym] = _as_series(
            combine_forecasts(fc, weights, fdm_s, cap=cfg.forecast_cap), index, f"combine_forecasts[{sym}]"
        )
    fdm = _frame(index, symbols, fdm_by_symbol)
    combined = _frame(index, symbols, combined_by_symbol)

    # 5./6. Volatility scalar and subsystem position (shares) per symbol.
    vol_scalar_df = _frame(
        index,
        symbols,
        {
            sym: _as_series(
                vol_scalar(s, pct_vol[sym].reindex(s.index), cfg.capital, cfg.tau), s.index, f"vol_scalar[{sym}]"
            )
            for sym, s in series_px.items()
        },
    )
    subsystem = _frame(
        index,
        symbols,
        {
            sym: _as_series(subsystem_position(vol_scalar_df[sym], combined[sym]), index, f"subsystem_position[{sym}]")
            for sym in symbols
        },
    )

    # 7. Instrument weights on close-to-close returns.
    instrument_weights = _instrument_weights(px, pct_vol, cfg)

    # 8./9. IDM on the subsystem returns (yesterday's shares × today's price change, over capital).
    subsystem_returns = subsystem.shift(1).mul(px.diff()).div(cfg.capital)
    idm = _as_series(
        rolling_idm(
            subsystem_returns,
            instrument_weights,
            min_periods=cfg.idm_min_periods,
            step=cfg.step,
            ewma_span=cfg.idm_ewma_span,
            corr_floor=0.0,
            dm_max=cfg.idm_max,
        ),
        index,
        "rolling_idm",
    )

    # 10. Portfolio positions (shares), sign-clipped and leverage-capped.
    raw_positions = portfolio_positions(
        subsystem,
        instrument_weights,
        idm,
        px,
        cfg.capital,
        long_only=cfg.long_only,
        max_leverage=cfg.max_leverage,
        short_only=cfg.short_only,
    )
    gross_before_cap = pd.Series(raw_positions.attrs.get("gross_before_cap"), dtype=float).reindex(index)
    leverage_capped = pd.Series(raw_positions.attrs.get("capped"), dtype=bool).reindex(index, fill_value=False)
    raw_positions.attrs.clear()
    positions = pd.DataFrame(raw_positions, dtype=float).reindex(index=index, columns=symbols)

    # 11. Buffering around the average absolute position.
    avg_abs = pd.DataFrame(
        average_abs_positions(vol_scalar_df, instrument_weights, idm), dtype=float
    ).reindex(index=index, columns=symbols)
    buffered = _frame(
        index,
        symbols,
        {
            sym: _as_series(
                apply_buffer(
                    positions[sym],
                    _as_series(position_buffer(avg_abs[sym], buffer_frac=cfg.buffer_frac), index, "position_buffer"),
                    trade_to_edge=True,
                ),
                index,
                f"apply_buffer[{sym}]",
            )
            for sym in symbols
        },
    )

    # 12. Weights: marked to market daily (diagnostic) and piecewise-constant for the engine.
    mtm = pd.DataFrame(positions_to_weights(buffered, px, cfg.capital), dtype=float).reindex(
        index=index, columns=symbols
    )
    target = _capped_piecewise_weights(buffered, mtm, cfg)

    validity = [
        vol_price.notna(),
        pct_vol.notna(),
        *[f.notna() for f in raw_forecasts.values()],
        *[f.notna() for f in scaled_forecasts.values()],
        fdm.notna(),
        combined.notna(),
        vol_scalar_df.notna(),
        subsystem.notna(),
        instrument_weights.notna(),
        positions.notna(),
        buffered.notna(),
        target.notna(),
    ]
    warmup_end = _warmup_end(validity, idm)

    return SystemOutput(
        prices=px,
        vol_price=vol_price,
        pct_vol=pct_vol,
        raw_forecasts=raw_forecasts,
        scaled_forecasts=scaled_forecasts,
        forecast_scalars=forecast_scalars,
        fdm=fdm,
        combined_forecast=combined,
        vol_scalar=vol_scalar_df,
        subsystem_positions=subsystem,
        instrument_weights=instrument_weights,
        idm=idm,
        positions=positions,
        buffered_positions=buffered,
        target_weights=target,
        warmup_end=warmup_end,
        subsystem_returns=subsystem_returns,
        mtm_weights=mtm,
        gross_before_cap=gross_before_cap,
        leverage_capped=leverage_capped,
        scalar_source=scalar_source,
        config=cfg,
    )


__all__ = [
    "ForecastScalarMode",
    "InstrumentWeighting",
    "SystemConfig",
    "SystemOutput",
    "TARGET_ABS_FORECAST",
    "run_system",
]
