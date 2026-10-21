# Anexo 7 — Sistemas sistemáticos completos y abiertos, y sus resultados reales

Reporte del agente de investigación (21-10-2026). [P]=primaria, [S]=secundaria.

## Hallazgos

### 1. Robert Carver — pysystemtrade y su cuenta real

**Arquitectura (código y docs, P).** Pipeline: `rawdata` (precios back-adjusted + vol diaria `mixed_vol_calc`: EWMA 35 días mezclada 30 % con la media de 10 años) → `rules` (forecast crudo) → `forecastScaleCap` (escalar a |f|≈10, tope ±20) → `combForecast` (pesos + FDM, re-tope ±20) → `positionSize` (vol targeting) → `portfolio` (pesos de instrumento × IDM, buffers) → `accounts` (P&L con costes). En producción (`docs/production.md`): orden de instrumento → orden de contrato → orden de bróker ejecutada por un algo (`algoOriginalBest`: límite pasivo que se vuelve agresivo; `market` si queda <1 h de sesión) sobre IBKR vía `ib_async`, puerto 4001, MongoDB + Parquet. El repo pasó a `pst-group` en enero 2026. **Solo futuros**: ETFs aparecen como "otro sistema hipotético".

**Reglas del repo** (`systems/provided/rules/`): `ewmac` (6 velocidades 2/8…64/256), `carry`, `breakout`, `accel`, `rel_mom`, `cs_mr`, `mr_wings`, `factors` [P].

**Resultados reales (año fiscal UK, al 5 de abril)** [blog qoppac, P]:

| Año | Futuros neto | AHL (vol-aj.) | SG CTA (vol-aj.) | Carver (vol-aj.) |
|---|---|---|---|---|
| 2024-25 (año 11) | **-16,3 %** (MTM -17,8 %, intereses +2,4 %, costes -0,9 %) | -18,7 % | -18,0 % | -15,4 % |
| 2025-26 (año 12) | **+23,7 %** | +30,3 % | +29,9 % | +25,9 % |

Serie vol-ajustada 2015→2026: 59,5 / 28,1 / 2,4 / 2,0 / 4,5 / 33,8 / -1,7 / 25,8 / -7,6 / 20,6 / -15,4 / 25,9 %. Desde abril 2014, con rf=0: **Sharpe 0,80, media 13,8 %, desv. 17,3 %** vs AHL 0,52 y SG CTA 0,54; correlación con SG 0,68 [2026-04-15, P]. 2024-25 fue "mi peor año", drawdown ≈17 %.

**Costes medidos**: 2025: slippage 56 pb + comisiones 29 pb + fees 5 pb; 2026: 55 + 33 + 4 pb. Sin el algo de ejecución el slippage habría sido 134 pb [2026-04-15, P]. Objetivo de vol **25 % anual**. Instrumentos: ~37 antes de la optimización dinámica (2021), "más de 110" después; 102 pasan su corte de coste. Capital: nunca lo publica ("relatively modest"; su benchmark supone "say $500K").

**Libros**: *Systematic Trading* (2015), *Smart Portfolios* (2017, ETFs long-only), *Leveraged Trading* (2019; Starter System: 1 instrumento, cruce 16/64, stop 0,5 × σ anual, capital mínimo £1.100/$1.500; **no ETFs**), *Advanced Futures Trading Strategies* (2023; 30 estrategias, 100+ instrumentos); quinto libro anunciado sept. 2026.

**ETFs**: Carver usa ETFs solo long-only (exige >£100 M de activos y excluye apalancados). Sobre ETFs apalancados: "no tienen lugar en la mayoría de carteras" [qoppac 2023-02-02, P]. Lo que transfiere: vol targeting, forecasts, buffers; lo que no: carry (sin curva), apalancamiento libre, coste de préstamo en cortos. El código contempla `long_only_instruments`.

### 2. Andreas Clenow

CIO de Acies Asset Management. **Sin track record público verificable.** Postura: "si aplicas un modelo de trend following estándar a acciones, pierdes"; su alternativa es momentum long-only con filtro de índice [2014-04-16, P]. Reglas de *Stocks on the Move*: universo S&P 500, ranking = pendiente de regresión exponencial anualizada (90 d) × R², top 20 %, filtro MA100 y gap >15 %, compras solo si SPX > MA200, tamaño = capital × 0,001 / ATR(20), re-dimensionar cada 2 semanas [S]. Crítica al retail: carteras aleatorias equiponderadas baten al índice; "¿tu modelo añade valor o es otro chimpancé?"; la mayoría de vendedores de sistemas son fraudes [2016-04-15, P].

### 3. Ernest Chan

Libros: *Quantitative Trading* (2009; 2.ª ed. 2021), *Algorithmic Trading* (2013), *Machine Trading* (2017), *Generative AI for Trading* (2025). Evidencia de decaimiento: su señal de insiders "se rompió sustancialmente" en 2014-15 [epchan 2017-07, P]; un tercero re-testó su *buy-on-gap*: Sharpe 3,58 (2005-07 sin costes) → tendencia descendente tras 2013 [S]. "El mayor mito es construir un sistema y cobrar pasivamente… quedan obsoletos muy rápido" [S]. Consejo: no apalancarse de más, pensar en media temporal (Kelly); "GenAI no genera alfa automatizada fiable" [2025, P].

### 4. Comunidades

- **Quantopian**: $48,8 M captados, Cohen comprometió $250 M (2016); live trading cerrado 2017; devolvió el dinero en feb. 2020 ("la estrategia market-neutral no daba resultados desde hacía al menos dos años" — Fawcett); cerrada 14-11-2020 [S]. **Wiecki et al. 2016** [P]: 888 algos; Sharpe IS→OOS **R² = 0,02**; más días de backtest → mayor *shortfall*; top-10 por random forest: Sharpe OOS 1,8 vs top-10 por Sharpe IS: 0,7.
- **QuantConnect Alpha Streams**: lanzado 2018, 80-90 % de rechazo; cerrado feb. 2022: el filtro "buscaba estrategias que funcionan en todos los regímenes" → sobreajuste; incluso el top 5 % "underperformed the S&P500"; alphas no correlacionadas "no fueron aditivas" [foro, P].
- **Collective2**: 193 sistemas (2009): mediana 30 d -1,9 % vs S&P +3,4 %, ~18 % bate; "real-life results are almost always vastly worse" [S].
- **Numerai**: 2024 +25,45 % neto, Sharpe 2,75 (autodeclarado); 2023 ≈ -17 %; AUM $60 M→$550 M [S].

### 5. Resultados realistas 2020-2025

| Año | SG CTA* | BTOP50 | 60/40 (VBIAX) |
|---|---|---|---|
| 2020 | +3,2 % | n/d | +16,4 % |
| 2021 | +6,2 % | n/d | +14,2 % |
| 2022 | +20,2 % | +14,9 % | -17,3 % |
| 2023 | -3,5 % | -1,9 % | +17,5 % |
| 2024 | +2,4 % | +5,5 % | +14,6 % |
| 2025 | -1,4 % (a nov.) | +3,1 % | +13,6 % |

*SG CTA vía Autumn Gold [S, verificar]; BTOP50 del portal BarclayHedge [P]; VBIAX de Zacks [S]. Académico: CTAs 1994-2007 exceso neto **85 pb/año** (no significativo), fees ≈4 % AUM; corregir supervivencia y backfill baja el retorno medio de 12,6 % a 4,9 % [Bhardwaj-Gorton-Rouwenhorst, NBER w14424, P]. Referencia de individuo serio: Carver, Sharpe ~0,8 (rf=0) y 12 años, con -16 % y DD 17 % a vol 25 %.

### 6. Ángulo contrario

- Bailey-Borwein-López de Prado-Zhu: con N=10 configuraciones aleatorias el máximo Sharpe IS esperado es **1,57** con OOS 0; **MinBTL < 2·ln N / E[max]²** años; 7 pruebas bastan para SR 1 espurio en 2 años [P].
- CFTC vs Parker/Baggett (2016): "robot" con "90 % de aciertos" nunca probado con dinero real [P].
- ETFs apalancados: dic-2008→abr-2009, índice Oil&Gas +2 % pero 2x -6 % y -2x -26 %; "no adecuados para más de una sesión" [FINRA 09-31, P].

## Contradicciones y huecos

1. **Backtest vs vivo de Carver**: su sistema con optimización dinámica backtestea SR neto 1,29 y en vivo lleva 0,76-0,80 tras 12 años → brecha ≈0,5 SR aun en el autor más riguroso.
2. **Shadow cost**: el post dice 250; `defaults.yaml` trae `shadow_cost: 50`.
3. Carver tabula 2025 como -14,7 % y -15,4 % para el mismo año.
4. Clenow "trend following no funciona en acciones" (2014) vs "momentum" vendido como tendencia; sin track record público.
5. "99 % sin edge" (Quantopian), supervivencia en Collective2/Darwinex, capital de Carver: **sin fuente primaria**.

## Qué adoptar en ibtrader (fórmulas y enlaces)

Base: `https://github.com/pst-group/pysystemtrade/blob/master/`

1. **Forecast crudo EWMAC** — `raw = (EWMA_fast(p) − EWMA_slow(p)) / σ_diaria(p)` en unidades de precio (`systems/provided/rules/ewmac.py`). Vol: `sysquant/estimators/vol.py::mixed_vol_calc` (35 d, 30 % de media 10 años).
2. **Escalado a |f|=10, tope ±20** — `scalar = 10 / mean_expanding(median_cross-sectional(|raw|))`, `min_periods=500` (`sysquant/estimators/forecast_scalar.py`). Escalares fijos: ewmac2_8 10,6 · 4_16 7,5 · 8_32 5,3 · 16_64 3,75 · 32_128 2,65 · 64_256 1,87 · carry 30. `forecast_cap: 20.0`.
3. **Combinación** — `f_comb = FDM · Σ w_i f_i`, re-topado a ±20; FDM = 1/√(w'Σw) con correlaciones flooreadas a 0, `dm_max 2.5`, suavizado EWMA 125 d. Ejemplo capítulo 15: 16_64 0,21 / 32_128 0,08 / 64_256 0,21 / carry 0,50, FDM 1,31.
4. **Vol targeting** (`systems/positionsizing.py`): `cash_vol_anual = capital · τ`; `cash_vol_diaria = cash_vol_anual / 16`; `block_value = precio · 0,01` por acción; `instr_value_vol = block_value · σ%_diaria`; `vol_scalar = cash_vol_diaria / instr_value_vol`; **`posición_subsistema = vol_scalar · f_comb / 10`**. τ por defecto 16 %; Carver 25 % con futuros; con ETFs el margen de IBKR acota τ.
5. **Cartera** (`systems/portfolio.py`): `posición = posición_subsistema · w_instr · IDM`; IDM igual que FDM con `dm_max 2.5`; pesos "handcraft" con `shrinkage_corr 0.5`; `long_only_instruments` para ETFs sin cortos.
6. **Buffering** (`systems/buffering.py`): `buffer = 0,10 · |vol_scalar · w_instr · IDM|`; `top/bot = posición ± buffer`; si la posición actual está dentro no se opera; si está fuera se opera **al borde**. Reduce rotación 5 % (reglas rápidas) a 30 % (lentas) [2023-02-01, P].
7. **Límite de velocidad**: costes ≤ 1/3 del SR pre-coste ⇒ ≈0,13 SR/año; `forecast_post_ceiling_cost_SR: 0.13` lo impone; descartar reglas rápidas por instrumento caro.
8. **Ejecución**: límite pasivo primero, agresivo con condiciones (`sysexecution/algos/algo_original_best.py`); medir slippage vs mid y comisiones en pb de capital/año (Carver: 85-88 pb a τ=25 %).
9. **Cuentas pequeñas**: *forecast mapping* con umbral antes que optimización dinámica; con ETFs el redondeo es menos lesivo que con futuros.
10. **Protocolo anti-sobreajuste**: registrar N pruebas, exigir años ≥ 2·ln N / SR², comparar contra carteras aleatorias (Clenow) y asumir brecha IS→OOS ≈ 0,5 SR (Carver, Wiecki).

## Fuentes

**Primarias**
- https://qoppac.blogspot.com/2026/04/annual-performance-update-year-12.html · https://qoppac.blogspot.com/2025/04/annual-performance-update-returneth.html · https://qoppac.blogspot.com/2018/04/trading-performance-year-four.html
- https://qoppac.blogspot.com/2021/11/mr-greedy-and-tale-of-minimum-tracking.html · https://qoppac.blogspot.com/2021/06/optimising-my-way-out-of-small-fund.html · https://qoppac.blogspot.com/2023/02/fast-but-not-furious-do-fast-trading.html · https://qoppac.blogspot.com/2016/01/pysystemtrader-estimated-forecast.html · https://qoppac.blogspot.com/2020/12/dynamic-trend-following.html
- https://github.com/pst-group/pysystemtrade (docs/backtesting.md, docs/production.md, sysdata/config/defaults.yaml, systems/positionsizing.py, systems/portfolio.py, systems/buffering.py, systems/provided/rules/ewmac.py, sysquant/estimators/forecast_scalar.py)
- https://www.harriman-house.com/leveragedtrading · https://www.harriman-house.com/advancedfuturestradingstrat
- https://www.followingthetrend.com/2014/04/trend-following-does-not-work-on-stocks/ · https://www.followingthetrend.com/2016/04/you-cant-beat-all-the-chimps/ · https://www.followingthetrend.com/2019/08/trading-evolved-errata-and-updates/
- https://epchan.blogspot.com/2017/ · https://epchan.blogspot.com/2020/07/what-is-probability-of-profit-of-your.html
- Wiecki, Campbell, Lent, Stauth (2016) "All that Glitters Is Not Gold": https://c.mql5.com/forextsd/forum/208/All%20that%20Glitters%20Is%20Not%20Gold%20-%20Comparing%20Backtest%20and%20Out-of-Sample%20Performance%20on%20a%20Large%20Cohort%20o.pdf
- Bailey, Borwein, López de Prado, Zhu "Pseudo-Mathematics and Financial Charlatanism": https://carmamaths.org/jon/backtest.pdf
- Bhardwaj, Gorton, Rouwenhorst NBER w14424: https://www.nber.org/system/files/working_papers/w14424/w14424.pdf
- https://www.quantconnect.com/forum/discussion/13441/alpha-streams-refactoring-2-0/ · https://www.quantconnect.com/forum/discussion/6737/9-ways-to-get-your-alpha-rejected/p1
- https://portal.barclayhedge.com/cgi-bin/indices/displayHfIndex.cgi?indexCat=Barclay-Investable-Benchmarks&indexName=BTOP50-Index
- https://www.finra.org/rules-guidance/notices/09-31 · https://www.cftc.gov/PressRoom/PressReleases/pr7469-16

**Secundarias**
- https://www.cxoadvisory.com/big-ideas/in-sample-vs-out-of-sample-performance-of-888-trading-strategies · https://www.cxoadvisory.com/?p=4128
- https://www.quantrocket.com/blog/quantopian-shutting-down/ · https://www.businessofbusiness.com/articles/how-quantopian-died-shut-down-quant-investment-robinhood/
- https://www.quantconnect.com/forum/discussion/10493/andreas-clenow-momentum-strategy-using-framework-from-stocks-on-the-move-book/p1
- https://financialnoob.substack.com/p/buy-on-gap-strategy-and-its-performance · https://quantnet.com/threads/interview-with-ernie-chan.9921/
- https://www.marketsmedia.com/jpmorgan-secures-500m-capacity-in-numerai/ · https://thefullfx.com/ctas-end-2025-on-a-positive-note/ · https://zacks.com/funds/mutual-fund/quote/VBIAX/performance
