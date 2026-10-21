# Anexo 3 — Construcción de portafolio, sizing y gestión de riesgo

Reporte del agente de investigación (21-10-2026). 22 búsquedas; fuentes leídas con WebFetch + pdftotext. [P]=primaria, [S]=secundaria.

## Hallazgos

### 1. Paridad de riesgo
- **Bridgewater, "The All Weather Story" (ene-2012) [P]**: cuatro cajas (crecimiento ↑/↓, inflación ↑/↓) con **"25% of risk"** en cada una (acciones, bonos nominales, bonos ligados a inflación, commodities); lanzada en 1996. *"Leverage is an implementation tool"*. **No publica vol objetivo ni Sharpe.**
- Vol objetivo real: memo de Bridgewater del 18-mar-2020 [P, DocumentCloud] lista **All Weather 10% vol (−12% YTD) y 12% vol (−14% YTD)**. Vol realizada desde inicio **10.7%** [Fortune 23-abr-2024, S].
- **AQR, Asness-Frazzini-Pedersen, FAJ 2012 [P, Tabla 2]**: 1926-2010, EE.UU.: RP sin apalancar = ~15% acciones/85% bonos, **vol 4.25%, SR 0.52**; RP apalancada a la vol del mercado (≈3.5×) → exceso **7.99% vs 3.84% mercado y 4.65% 60/40; SR 0.53 vs 0.25 vs 0.40**. **Sin costos de financiamiento** (lo admiten).
- **AQR, "Can Risk Parity Outperform If Yields Rise?" (2013) [P]**: 1947-2013 RP simple SR **0.74** vs 60/40 0.48; **en subida brusca de tasas (oct-79–sep-81) RP SR −1.35**.
- Contra: **Anderson-Bianchi-Goldberg (2012) [P]**: con costos de transacción 1926-2010, 60/40 y mercado baten a RP apalancada.
- **2022**: All Weather 10% vol **−22%** [Fortune, S]; RPAR −22.8% vs AOR (60/40) −16% [etf.com, S]. RP por debajo del 60/40 **cada año desde 2019**; AUM de RP $160 bn (2021) → $90 bn (fin 2023) [Fortune].
- 2020: All Weather 10% vol **+9.47%**; HFR RP 10% **+3.6%** vs S&P RP 10% pasivo **+11.5%** [Institutional Investor, S]. ECB FSR may-2020 [P institucional]: ~$300 bn en ~100 fondos RP; su modelo a 8% vol tuvo que vender **≈225% del capital** en marzo 2020.

### 2. Volatility targeting
- **Moreira & Muir (JF 2017) [P, Tabla I]**: peso = c/σ²(mes anterior). Mercado: **alfa 4.86%/año, Sharpe +25%**. Momentum alfa 12.5%, ROE, carry, RMW funcionan; **SMB y CMA no.** Apalancamiento: mediana ≈1, p90 2.6, **p99 6.4**; sobrevive 1-14 pb de costos.
- **Cederburg-O'Doherty-Wang-Yan (JFE 2020) [P]**: 103 estrategias; vol-managed gana Sharpe solo en **53/103**; implementable en tiempo real es **peor en 72/103**; sobrevive en **momentum, ROE y BAB**.
- **Harvey et al. / Man AHL (JPM 2018) [S]**: >60 activos desde 1926, objetivo 10%: **acciones SR 0.40 → 0.48-0.51; bonos, divisas y commodities: efecto despreciable**; cola izquierda reducida en todos; mejora Sharpe y max DD del 60/40 y de RP.
- **Carver (blog, jul-2018) [P practicante]**: 37 futuros, tendencia: **SR 0.92 con vol targeting vs 0.57 sin**; quitarlo cuesta "un tercio del Sharpe".

### 3. Tendencia / CTA
- **Moskowitz-Ooi-Pedersen (JFE 2012) [P]**: 58 futuros 1985-2009; señal = signo del exceso a 12 meses, tenencia 1 mes; cada posición escalada a **40% vol ex-ante**. Diversificado: **SR bruto >1**, alfa 1.58%/mes; explica por completo el índice Managed Futures. **Sin cifras netas.**
- **Hurst-Ooi-Pedersen (JPM 2017) [P]**: 67 mercados 1880-2016, señales 1/3/12 meses, **10% vol objetivo**, costos + 2/20: positivo **en cada década** neto; SR medio **por mercado ≈0.4 bruto**; positivo en 8 de los 10 peores drawdowns del 60/40; peor con correlaciones altas (**fin 2008–mediados 2014**).
- **SG Trend Index**: **2022 +27.4%** (ACWI −18.4%), 2008 +20.9%; may-24→may-25 **−20.4%**, 2.º mayor DD desde 2000 [Cambridge Associates 2025, S]. **Graham Capital (jul-2022) [P industria]**: IR del índice **0.53 desde 2000**; **desinvertir en drawdown destruye valor** (IR 0.52 → 0.30/0.09/0.03 con stops a −15/−10/−5%).
- **Baltas-Kosowski [P resumen]**: mejores estimadores de vol cortan turnover >1/3 sin perder; debilidad post-2008 ligada a correlaciones.
- **Antonacci GEM [S]**: 1974-2013 CAGR 17.43%, **SR 0.87, MDD 22.7%**; el lookback de 12 m fue el mejor de 1-48 probados (selección en muestra). Sin track 2015-2024.

### 4. Sizing: Kelly y Carver
- **Thorp (2006) [P]**: S&P con m=.11, s=.15, r=.06 → **f* = 2.22× apalancamiento**. P(caer alguna vez a fracción x) = **x^(2m/s²)**; con Kelly completo: 50 % de perder la mitad. "Overbetting is much more severely penalized than underbetting"; elegir **0.5f* ≤ f < f*** cuesta ≤25% de crecimiento.
- Relación con vol targeting: en Kelly continuo la **vol óptima del portafolio = Sharpe** (SR 0.5 → 50% vol; medio Kelly 25%).
- **Carver, Systematic Trading [S de P]**: "full Kelly is far too aggressive… Half-Kelly"; sistema SR ≈1.0 neto → **máximo 37%** de vol; "SR consistently greater than 1.0 are rarely achieved"; aplicar **0.75× al backtest**; costos **≤ 1/3 del SR bruto**; no operar si la posición está dentro del 10% del objetivo. **pysystemtrade docs [P]**: ejemplo con **25% vol objetivo**, forecast medio 10 / tope 20, FDM 1.1, IDM 1.5, EWMAC 8/32 y 32/128; sistema simple SR neto 0.53. Su sistema real (dic-2021, IBKR, ~114 instrumentos): std anual 23%, costos 1.06%/año; backtest SR 1.31 que él mismo llama "massively better than realistic".

### 5. Construcción con costos
- **Gârleanu-Pedersen (JF 2013) [P]**: operar solo parte del camino hacia un "aim" que subpondera señales de decaimiento rápido. Señales 5 d / 1 a / 5 a: SR bruto sin costos 0.79 → **neto −18** si se opera ingenuamente; óptimo dinámico **0.54 neto vs 0.44 estático**.
- **HRP, López de Prado (JPM 2016) [S]**: Monte Carlo 10 activos: varianza fuera de muestra CLA 0.1157, inverse-vol 0.0928, **HRP 0.0671**.
- **DeMiguel-Garlappi-Uppal (RFS 2009) [P]**: 14 modelos, 7 datasets: ninguno bate 1/N de forma consistente; media-varianza necesita **~3.000 meses con 25 activos**.
- Black-Litterman: no verificado con fuente primaria.

### 6. Límites operativos
Solo fuentes secundarias sin atribución: Millennium **recorte ~5% desde el HWM, liquidación 7.5-10%**; límites por nombre 1-3%, industria 5-15%, neto ±10%; el equipo de riesgo decide, no el PM [Substack]. **Ninguna cifra publicada por las firmas.**

### 7. Ángulo contrario
- RP ya tenía su falla documentada: AQR 2013 muestra SR −1.35 en subidas bruscas de tasas; 2022 lo repitió (AW −22%).
- 2020: el daño vino del **desapalancamiento discrecional** (pasivo +11.5% vs gestores +3.6%). ECB: pro-ciclicidad.
- Vol targeting: equivale a momentum (vende tras caídas); Cederburg: falla en tiempo real para la mayoría de factores; Carver: reduce skew. Graham: cualquier regla de salida por drawdown sobre tendencia pierde.
- Kelly: Thorp advierte no-estacionariedad; estimador plug-in sesgado hacia arriba [arXiv 2503.17927, S].

## Contradicciones y huecos
- Net Sharpe de Hurst et al.: Swedroe 0.76 vs CXO 0.4; el 0.4 del texto primario es **por mercado y bruto**.
- Moreira-Muir (+25% Sharpe) vs Cederburg (72/103 peor en tiempo real): la mejora real existe solo en momentum/ROE/BAB y en activos de riesgo; nula en bonos y commodities.
- RP: AQR (SR 0.53-0.74 bruto) vs Anderson et al. (pierde con costos) vs realidad 2019-2023 (debajo del 60/40).
- Límites de pods: cero disclosure primaria. Black-Litterman, MacLean-Thorp-Ziemba y el PDF de Harvey et al. no se pudieron leer. Antonacci sin resultados post-2015.

## Receta defendible para un individuo con IBKR (~10 ETFs)
1. **Núcleo risk-parity por cajas** (Bridgewater): acciones globales, Treasuries intermedios y largos, TIPS, oro/commodities, pesos inverse-vol o HRP, **nunca Markowitz sin regularizar** (DeMiguel). Sin apalancar rinde SR ~0.5-0.6 a 4-6% vol.
2. **Overlay de tendencia** por ETF: promedio de señales 1/3/12 meses (Hurst), rebalanceo mensual; largo si señal >0, en T-bills (SGOV/BIL) si <0. Esperar SR por activo ~0.3-0.4 bruto; con 10 ETFs y correlación ~0.3, **0.6-0.8 bruto** diversificado.
3. **Vol target 10% del portafolio** (Harvey/Bridgewater), estimada con vida media ~20 días o 1-3 meses, **tope de apalancamiento 1.5×**. Con SR esperado 0.6, Kelly completo sería 60% vol; 10% es ~1/6 Kelly, dentro del "nunca más de medio Kelly" de Carver/Thorp.
4. **Costos**: regla de Carver (≤1/3 del SR bruto), no operar si la posición está a <10% del objetivo, trade parcial hacia el objetivo (Gârleanu-Pedersen).
5. **Sharpe neto realista: 0.5-0.8** (backtest × 0.75, Carver); retorno excedente ~5-8% a 10% vol; **esperar drawdowns de 15-25% aun a 10% vol** (AW −22% en 2022, GEM −22.7%, SG Trend −20%).
6. **Límites ex-ante, no timing**: a −20% desde HWM bajar el vol target a 5%; a −30% parar y revisar el modelo. Graham demuestra que salir por drawdown "para mejorar" destruye valor: el límite es para sobrevivir (Thorp), no para ganar.
7. **Benchmarks**: AOR (60/40, −16% 2022), RPAR (All Weather vía ETFs, −22.8% 2022), HFR RP 10% vol, SG Trend Index para el overlay.

## Fuentes
**Primarias**
- Bridgewater, The All Weather Story (2012): https://www.bridgewater.com/research-and-insights/the-all-weather-story
- Bridgewater memo 18-mar-2020: https://assets.documentcloud.org/documents/6812567/Bridgewater-memo-3-18-2020.pdf
- Asness, Frazzini, Pedersen, Leverage Aversion and Risk Parity (FAJ 2012): https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Leverage-Aversion-and-Risk-Parity.pdf
- AQR, Can Risk Parity Outperform If Yields Rise? (2013): https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/AQR-Can-Risk-Parity-Outperform-If-Yields-Rise.pdf
- Anderson, Bianchi, Goldberg (2012): https://cdar.berkeley.edu/sites/default/files/2012_Anderson-et-al.-WillRiskStrategyOutperfom.pdf
- Moreira & Muir, Volatility-Managed Portfolios (JF 2017): https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf
- Cederburg, O'Doherty, Wang, Yan (JFE 2020): https://www.lehigh.edu/~xuy219/research/COWY.pdf
- Moskowitz, Ooi, Pedersen, Time Series Momentum (JFE 2012): https://fairmodel.econ.yale.edu/ec439/jpde.pdf
- Hurst, Ooi, Pedersen, A Century of Evidence on Trend-Following Investing (JPM 2017): https://fairmodel.econ.yale.edu/ec439/hurst.pdf
- Baltas & Kosowski, Demystifying Time-Series Momentum Strategies: https://papers.ssrn.com/abstract=2140091
- Thorp, The Kelly Criterion in Blackjack, Sports Betting and the Stock Market (2006): https://www.gwern.net/doc/statistics/decision/2006-thorp.pdf
- Gârleanu & Pedersen, Dynamic Trading with Predictable Returns and Transaction Costs (JF 2013): https://archive.nyu.edu/bitstream/2451/28346/2/DynamicTrading.pdf
- López de Prado, Building Diversified Portfolios that Outperform Out-of-Sample (2016): https://papers.ssrn.com/abstract=2708678
- DeMiguel, Garlappi, Uppal, Optimal Versus Naive Diversification (RFS 2009): https://ideas.repec.org/a/oup/rfinst/v22y2009i5p1915-1953.html
- Harvey et al., The Impact of Volatility Targeting (JPM 2018): https://scholars.duke.edu/publication/1370354
- Carver, pysystemtrade docs: https://github.com/robcarver17/pysystemtrade/blob/master/docs/introduction.md · Vol targeting and trend following (2018): https://qoppac.blogspot.com/2018/07/vol-targeting-and-trend-following.html · My trading system (2021): https://qoppac.blogspot.com/2021/12/my-trading-system.html
- Graham Capital, Timing Trend Following (jul-2022): https://www.grahamcapital.com/wp-content/uploads/2023/08/Timing-Trend-Following_July-2022.pdf
- ECB FSR, Volatility-targeting strategies and the market sell-off (may-2020): https://www.ecb.europa.eu/pub/financial-stability/fsr/focus/2020/html/ecb.fsrbox202005_02~f6616db9be.en.html

**Secundarias**
- Fortune (23-abr-2024): https://fortune.com/2024/04/23/lackluster-returns-ray-dalio-investing-strategy-investors-pull-billions
- Institutional Investor (2021): https://www.institutionalinvestor.com/article/2bswpyzz05fjtwnke2qdc/portfolio/not-all-risk-parity-strategies-sucked-last-year
- etf.com (2024): https://www.etf.com/sections/news/risk-parity-fails-keep-pace-6040-model
- Cambridge Associates (2025): https://www.cambridgeassociates.com/insight/does-trend-followings-recent-struggle-signal-that-the-strategy-is-structurally-broken/
- Quantpedia sobre Harvey et al.: https://quantpedia.com/the-impact-of-volatility-targeting-on-equities-bonds-commodities-and-currencies
- CXO Advisory sobre Carver: https://www.cxoadvisory.com/big-ideas/a-few-notes-on-systematic-trading
- Wikipedia, Hierarchical Risk Parity: https://en.wikipedia.org/wiki/Hierarchical_Risk_Parity
- Swedroe/ETF.com sobre Hurst et al.: https://www.etf.com/sections/index-investor-corner/swedroe-why-trend-following-works
- Alpha Architect, Dual Momentum: https://alphaarchitect.com/book-review-dual-momentum-investing/
- Substack youngandcalculated (sin fuente): https://youngandcalculated.substack.com/p/risk-management-inside-a-pod-how
- arXiv 2503.17927, sesgo del estimador Kelly: https://www.arxiv.org/pdf/2503.17927
- SG, CTA update 2025: https://content.sgmarkets.com/CTA_UPDATE_KEEPING_UP_WITH_THE_TRENDFOLLOWERS_2025
