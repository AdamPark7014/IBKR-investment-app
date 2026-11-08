"""Target weights for today from the configured strategy (audit 2026-11-07, §5 step 2).

One function, three strategy kinds selected by ``STRATEGY__NAME``:

* ``pipeline``: the phase-2 stage graph (``pipeline.system.run_system``), the same code the
  backtest and ``research-portfolio`` use (research → production parity). ``STRATEGY__PARAMS``
  may override any ``SystemConfig`` field (``rules``, ``instrument_weighting``, ``tau``...).
* ``static``: fixed weights from ``STRATEGY__PARAMS__WEIGHTS`` (e.g. the 60/40 control, or
  plain indexing if research says nothing beats it).
* ``sma_crossover``: legacy single-rule signal, equal weight across symbols that are "on".
  Kept only so old freezes still run; research already rejected it.

The weights are the last row of the strategy output. Before the pipeline's warm-up ends the
answer is "all cash", never an implicit position.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Mapping, Optional, Tuple

import pandas as pd

from ..config import AppSettings
from ..data.universe import UniverseSpec


def _system_config(settings: AppSettings, symbols: list[str], spec: Optional[UniverseSpec]) -> Any:
    from ..pipeline.system import SystemConfig

    fields = {f.name for f in dataclasses.fields(SystemConfig)}
    params = {k: v for k, v in dict(settings.strategy.params or {}).items() if k in fields}
    if "rules" in params and not isinstance(params["rules"], tuple):
        params["rules"] = tuple(params["rules"])
    boxes = {e.symbol: e.box for e in spec.entries if e.symbol in symbols} if spec is not None else None
    params.setdefault("boxes", boxes)
    params.setdefault("capital", float(settings.pretrade.capital_usd or 100_000.0))
    params.setdefault("long_only", settings.trading.direction == "long_only")
    params.setdefault("short_only", settings.trading.direction == "short_only")
    params.setdefault("max_leverage", float(settings.pretrade.max_gross_exposure))
    return SystemConfig(**params)


def compute_target_weights(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    spec: Optional[UniverseSpec] = None,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Return ``(weights, meta)``. ``meta`` says which strategy, as-of date and why weights are 0."""
    name = str(settings.strategy.name).lower()
    symbols = sorted(data)
    meta: Dict[str, Any] = {"strategy": name, "symbols": symbols}
    if not data:
        meta["reason"] = "no_data"
        return {}, meta
    closes = pd.DataFrame({s: pd.Series(df["close"], dtype=float) for s, df in data.items()}).sort_index()
    closes.index = pd.DatetimeIndex(closes.index)
    meta["as_of"] = str(closes.index.max().date())
    # A symbol without a bar on the last date has no target today: it is left out (held as is)
    # instead of reading NaN as 0 and selling it because one provider was late.
    stale = sorted(s for s in symbols if pd.isna(closes[s].iloc[-1]))
    if stale:
        meta["stale_symbols"] = stale

    if name == "static":
        raw = dict((settings.strategy.params or {}).get("weights") or {})
        weights = {str(k).upper(): float(v) for k, v in raw.items()
                   if str(k).upper() in data and str(k).upper() not in stale}
        missing = sorted(set(str(k).upper() for k in raw) - set(weights))
        if missing:
            meta["missing_symbols"] = missing
        return weights, meta

    if name == "pipeline":
        from ..pipeline.system import run_system

        cfg = _system_config(settings, symbols, spec)
        out = run_system(closes, cfg)
        meta["warmup_end"] = str(out.warmup_end.date()) if out.warmup_end is not None else None
        last = closes.index.max()
        if out.warmup_end is None or last < out.warmup_end:
            meta["reason"] = "pipeline_warmup"
            return {s: 0.0 for s in symbols}, meta
        row = out.target_weights.reindex(columns=symbols).loc[last]
        return {s: float(0.0 if pd.isna(row[s]) else row[s]) for s in symbols if s not in stale}, meta

    if name == "sma_crossover":
        from ..strategy.sma_crossover import SMACrossover

        p = dict(settings.strategy.params or {})
        strat = SMACrossover(int(p.get("fast_window", 10)), int(p.get("slow_window", 30)), allow_short=False)
        sig = strat.generate_signals(dict(data))
        on = [s for s in symbols if len(sig[s]) and int(sig[s].iloc[-1]) > 0]
        meta["legacy"] = "rejected by research (audit 2026-11-07); kept for old freezes"
        return {s: (1.0 / len(on) if s in on else 0.0) for s in symbols if s not in stale}, meta

    raise ValueError(f"unknown STRATEGY__NAME={settings.strategy.name!r} (pipeline | static | sma_crossover)")


__all__ = ["compute_target_weights"]
