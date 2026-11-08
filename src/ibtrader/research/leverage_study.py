"""Estudio de apalancamiento: ¿qué haría 1,5× a configuraciones YA probadas, pagando el margen?

No es un candidato nuevo ni pasa por la compuerta: no elige nada entre variantes. Toma configuraciones que
ya están en el registro de pruebas, las corre con distintos topes de exposición bruta y cobra el interés
de margen sobre el efectivo negativo (``backtest(margin_rate_annual=...)``). Sirve para una sola cosa:
que Adam decida el apalancamiento con números honestos (retorno, caída y coste del préstamo).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from ..backtest.engine import backtest
from ..config import AppSettings
from ..data.universe import UniverseSpec
from ..engine.targets import min_trade_frac_for
from ..pipeline.system import SystemConfig
from ..risk.manager import RiskManager, RiskState
from ..strategy.pipeline_strategy import PipelineStrategy
from .portfolio_runner import CORE_TREND_RULES, CORE_TREND_WEIGHTS, INITIAL_EQUITY, _window_stats, close_frame

Config = Tuple[str, Tuple[str, ...], str, Optional[Dict[str, float]]]

#: Configuraciones ya evaluadas con datos reales el 2026-11-08 (ninguna es nueva).
DEFAULT_CONFIGS: Tuple[Config, ...] = (
    ("pipeline_static_box_risk_parity", ("long_const",), "box_risk_parity", None),
    ("pipeline_ewmac_hrp", ("ewmac16_64", "ewmac32_128", "ewmac64_256"), "hrp", None),
    ("pipeline_core_trend_box_risk_parity", CORE_TREND_RULES, "box_risk_parity", dict(CORE_TREND_WEIGHTS)),
)


def run_leverage_study(
    data: Mapping[str, pd.DataFrame],
    settings: AppSettings,
    universe: UniverseSpec,
    *,
    leverages: Sequence[float] = (1.0, 1.5),
    margin_rate_annual: float = 0.06,
    configs: Iterable[Config] = DEFAULT_CONFIGS,
) -> Dict[str, Any]:
    prices = close_frame(dict(data))
    symbols = list(prices.columns)
    boxes = {e.symbol: e.box for e in universe.entries if e.symbol in symbols}
    capital = INITIAL_EQUITY
    rows: List[Dict[str, Any]] = []
    for cid, rules, weighting, rule_weights in configs:
        start: Optional[pd.Timestamp] = None
        for lev in leverages:
            cfg = SystemConfig(
                rules=tuple(rules), rule_weights=rule_weights, instrument_weighting=weighting,  # type: ignore[arg-type]
                boxes=boxes, capital=capital, long_only=True, max_leverage=float(lev),
                min_trade_frac=min_trade_frac_for(settings, capital),
            )
            risk_cfg = settings.risk.model_copy(update={
                "max_total_exposure_pct": max(float(settings.risk.max_total_exposure_pct), 100.0 * float(lev)),
            })
            strategy = PipelineStrategy(cfg)
            res = backtest(
                data=dict(data), strategy=strategy, commission_cfg=settings.commission,
                slippage_cfg=settings.slippage, initial_equity=capital, direction="long_only",
                risk_manager=RiskManager(risk_cfg, RiskState(starting_equity_today=capital)),
                reg_fees_cfg=settings.reg_fees, margin_rate_annual=float(margin_rate_annual) if lev > 1.0 else 0.0,
            )
            out = strategy.last_output
            if start is None:  # misma ventana para todos los niveles de una configuración
                start = out.warmup_end if out is not None else None
            if start is None:
                rows.append({"config": cid, "leverage": lev, "error": "sin calentamiento"})
                continue
            st = _window_stats(res, start, capital)
            years = float(st.get("years") or 0.0)
            fin = res.financing.loc[start:] if len(res.financing) else res.financing
            rows.append({
                "config": cid, "leverage": float(lev),
                "cagr": st.get("cagr"), "vol": st.get("volatility"),
                "sharpe": st.get("sharpe"), "max_drawdown": st.get("max_drawdown"),
                "coste_operar_anual_pct": st.get("cost_drag_annual_pct"),
                "interes_margen_anual_pct": (float(fin.sum()) / capital / years * 100.0) if years > 0 else 0.0,
                "desde": st.get("oos_start"), "hasta": st.get("oos_end"),
            })
    return {
        "nota": "Estudio para decidir el apalancamiento; no es una prueba nueva ni elige entre variantes.",
        "tipo_margen_anual": margin_rate_annual,
        "filas": rows,
    }


__all__ = ["DEFAULT_CONFIGS", "run_leverage_study"]
