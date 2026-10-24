"""Grafo de stages del sistema (rawdata → forecast → combine → size → portfolio); ver docs/research.

Fase 2 del playbook: la cadena de pysystemtrade adaptada a ETFs, una función pura por paso,
todas point-in-time (el valor en ``t`` solo usa información hasta ``t``; el engine opera en ``t``
con la señal de ``t - 1``):

1. :mod:`ibtrader.pipeline.vol` -- ``price_vol_daily`` / ``pct_vol_daily``: vol EWMA(35) de las
   diferencias diarias de precio, mezclada 30 % con la media de 10 años y con suelo en el cuantil 5 %.
2. :mod:`ibtrader.pipeline.rules` -- forecasts crudos: ``ewmacF_S`` (cruce de EWMA sobre vol) y
   ``tsmom_1_3_12`` (momentum 1/3/12 meses sobre vol); ``run_rules`` recorre regla x símbolo.
3. :mod:`ibtrader.pipeline.forecast` -- ``estimate_forecast_scalar`` (pooled entre símbolos para que
   el |forecast| medio sea 10) y ``scale_and_cap`` (``+/- 20``).
4. :mod:`ibtrader.pipeline.combine` -- ``forecast_div_multiplier`` (FDM con correlaciones expandiendo)
   y ``combine_forecasts`` (suma ponderada, re-topada).
5. :mod:`ibtrader.pipeline.sizing` -- ``vol_scalar`` (acciones a forecast 10 para un objetivo de vol
   ``tau``), ``subsystem_position``, ``position_to_weight``.
6. :mod:`ibtrader.pipeline.buffering` -- ``position_buffer`` / ``apply_buffer`` (operar al borde de una
   banda de ``+/- 10 %`` alrededor del objetivo para recortar rotación).

``pipeline.system`` y ``pipeline.portfolio_stage`` encadenan estos pasos.
"""

from __future__ import annotations

from . import buffering, combine, forecast, rules, sizing, vol

__all__ = ["buffering", "combine", "forecast", "rules", "sizing", "vol"]
