# Anexo 6 — Datos alternativos y machine learning: qué funciona de verdad

Reporte del agente de investigación (21-10-2026). 22 búsquedas, 14 fuentes leídas con WebFetch y 6 papers completos extraídos de PDF (GKX 2020, McLean-Pontiff 2016, Jensen-Kelly-Pedersen 2023, Fischer-Krauss 2017, AQR "Century of Evidence", informe Lowenstein 2025). SSRN, S&P Global (SPIVA), NBER y Alpha Architect bloquearon el acceso. (P)=primaria, (S)=secundaria.

## Hallazgos

### 1. Datos alternativos: qué compran, cuánto cuesta, qué decae

- Gasto de gestores en alt-data 2025: ≈ **$2.8 bn, +17 % interanual**; 2.805 datasets en Scout; **≈20 clientes por dataset** (25 en 2024) [Neudata, 23-feb-2026, P].
- Comprador medio: **$1.6 M/año, 20 proveedores, ≈$80 k por dataset**; multi-estrategia grandes ≈ **$5 M/año con 43 proveedores** [Hedgeweek citando Neudata, 19-sep-2024, S].
- Encuesta Lowenstein 2025: **90 % usa alt-data** (67 % en 2024); más de dos tercios con presupuesto > $1 M [P]. Sus cifras de mercado global ($40 bn en 2030) **no cuadran** con Neudata 2026 ($23.1 bn en 2030): alcances distintos.
- Alfa documentada: imágenes satelitales de estacionamientos de 44 minoristas (2011–2017) → **4–5 % en los 3 días alrededor del reporte trimestral**, sin mejora del price discovery [Katona, Painter, Patatoukas, Zeng, JFQA 2025, P abstract].
- Ventas en tiempo real (≈50 M dispositivos móviles) → **3.4 % de exceso de retorno en el anuncio** [Froot, Kang, Ozik, Sadka, JFE 2017, P abstract].
- Crowding: "not a lot" de alfa (Domeyard), "mucho es ruido" (Man Group) [Risk.net, S].
- Individuo: Quiver Quantitative $12.5–25/mes [S]. A $56–80 k por dataset institucional, tarjetas, satélite y geolocalización **no son comprables**; sí se puede construir scraping propio, EDGAR, tendencias de búsqueda y flujo de opciones (sin fuente que mida su alfa).

### 2. ML con evidencia real

- **Gu, Kelly, Xiu (RFS 2020)** [P, leída completa]: ~30.000 acciones, 1957–2016, 920 features. **R² mensual fuera de muestra**: OLS-3 (tamaño, valor, momentum) 0.16 %; PLS 0.27 %; **RF 0.33 %; GBRT 0.34 %; NN3 0.40 % (máximo)**; NN4-NN5 no mejoran ("los beneficios del deep learning son limitados"). Sharpe decil largo-corto ponderado por valor: OLS-3 0.61, RF 0.98, NN3 1.20, **NN4 1.35**; **rotación 120–150 %/mes**, drawdowns 30–70 %. Predictores dominantes: momentum, liquidez, volatilidad.
- **Kelly, Malamud, Zhou (JF 2024)**: R² y Sharpe suben con parámetros > observaciones. Crítica de Buncic: el resultado depende de restringir el intercepto a cero; **es shrinkage, no complejidad** [S]. Réplica Kelly & Malamud (AQR, jul-2025) [P abstract]. Disputa abierta.
- **Avramov, Cheng, Metzker (Mgmt Sci 2023)** [S]: retorno ajustado 0.75–1.88 %/mes, pero **−62 % sin microcaps, −68 % sin empresas no calificadas, −80 % sin empresas en distress**.
- Meta-labeling: **ninguna evidencia revisada por pares que aísle su aporte**; solo informes de Hudson & Thames (vendedor) [S].
- Regímenes HMM: Nystrup (DTU 2014) bate rebalanceo tras costos sin cifras públicas [P resumen]; índices asiáticos: bate buy-and-hold en 3 de 5 mercados, **falla en Hong Kong** [S]; RL con regímenes: gana in-sample, **no reproduce OOS** [S].
- **LLMs — Lopez-Lira & Tang v6 (28-oct-2025)** [P, leída]: GPT-4 largo-corto a un día: **Sharpe 2.97 bruto**; con 5 pb >300 % acumulado, **20 pb no rentable**; rotación ≈190 %/día; **Sharpe cae 6.54 (4T21) → 3.68 (2022) → 2.33 (2023) → 1.22 (ene-may 2024)**.

### 3. Lo que no funciona

- **Fischer & Krauss (2017/18)** [P, leída]: LSTM sobre S&P 500 1992–2015, Sharpe 5.8 bruto. Por periodos: 1993–2000 >11 USD por 1 USD/día; **2010–2015 "deterioro": el random forest pierde y el LSTM "mantiene el capital aproximadamente constante tras costos"** — cero ventaja reciente.
- Brasil [Chague, De-Losso, Giovannetti 2019 vía Quantpedia, S]: 19.646 iniciaron day-trading 2013–2015; de los 1.551 que persistieron 300+ días, **97 % perdió**; 1.1 % superó el salario mínimo.
- Barber & Odean 2000 [P]: 66.465 hogares 1991–1996; los más activos **11.4 % vs mercado 17.9 %**.
- Señal/ruido: con 0.4 % de R² mensual en el mejor modelo de GKX, el R² diario de un ETF es del orden de 0.01–0.02 % (inferencia del agente).

### 4. Cómo evitan el overfitting los fondos

- GKX: sin cross-validation barajada ("para mantener el orden temporal"), muestra de validación para hiperparámetros, pérdida de Huber, reajuste anual recursivo, modelos someros (RF con 1–5 niveles, NN3) [P].
- Microestructura: **miles de millones de observaciones**, un modelo universal pooled entre acciones bate a los específicos [Sirignano & Cont 2018, P]. Contraste: un ETF diario tiene ~5.000 observaciones.
- Nowcasting: Froot et al. y Katona predicen **ventas/sorpresas de beneficios**, no precios.
- Umbral t > 3.0 [Harvey-Liu-Zhu]; shrinkage bayesiano [JKP]; ejemplo de Bailey et al.: Sharpe 1.59 in-sample → −0.18 OOS [Quantpedia, S].

### 5. Primas con décadas de evidencia

- **AQR "Century of Evidence"** [P, leída]: 67 mercados, 1880–2013, lookbacks 1/3/12 meses equiponderados; **14.9 % bruto, 11.2 % neto de 2/20, vol 9.7 %, Sharpe neto 0.77, correlación 0.00 con acciones EE.UU.**; por década de 0.13 (1910s) a 1.70 (1970s), 2000–2013: 0.62; los 10 mayores drawdowns −13.5 % a −26.3 % con recuperaciones de hasta 75 meses; con Sharpe futuro supuesto de 0.4, 20 % en un 60/40 sube el Sharpe de 0.38 a 0.46 y baja el drawdown máximo de 62 % a 51 %.
- Moskowitz-Ooi-Pedersen 2012: 58 futuros; el retorno de 12 meses predice ~1 año y luego revierte parcialmente [P resumen].
- Frazzini-Israel-Moskowitz: $1–1.7 bn de operaciones reales 1998–2016; costos reales **<1/10 de lo estimado antes**; valor y momentum escalan [S].
- Ilmanen: Sharpe hipotético pre-costos >2 para mezcla long/short de estilos; conservador 0.7–0.8 [S].
- Valor: "la muerte del valor es prematura" [Israel, Laursen, Richardson, JPM 2021, P]. **Hueco**: cifras del drawdown 2018–2020.

### 6. Ángulo contrario

- Harvey-Liu-Zhu (RFS 2016): **316 factores**; hurdle **t > 3.0**; **1/3–1/2 probablemente falsos** [S].
- **McLean-Pontiff (JF 2016)** [P]: **0.582 %/mes in-sample → 0.402 % OOS → 0.264 % post-publicación: −26 % y −58 %**.
- **Jensen-Kelly-Pedersen (JF 2023)** [P]: 153 factores, 93 países; **replicación EE.UU. 82.4 %**; citan a Chen & Zimmermann: la caída post-publicación corregida es **solo 12 %**.
- SPIVA fin-2025 [S; PDF bloqueado]: **79 % de fondos large-cap activos perdieron contra el S&P 500 en 2025**; persistencia: **4.5 %** se mantuvo en la mitad superior 5 años.

## Contradicciones y huecos

- **Tamaño del mercado de alt-data**: $2.8 bn (Neudata 2026, gasto de gestores) vs ">$15 bn global" (Lowenstein). Usar la cifra de Neudata.
- **Decaimiento post-publicación**: 58 % (McLean-Pontiff) vs 12 % corregido (Chen-Zimmermann) vs "la mayoría replica" (JKP) vs "la mayoría es falsa" (HLZ). Lo compatible: los factores existen, pero el retorno realizado tras publicarse es ~la mitad del backtest.
- **Virtud de la complejidad**: KMZ vs Buncic; la réplica es del propio autor.
- **ML en acciones**: GKX predice mejor en large caps; Avramov dice que el *retorno* cae 62–80 % sin microcaps. Ambos ciertos: predecir ≠ capturar.
- Huecos: SPIVA 15/20 años; valor 2018–2025; meta-labeling revisado; capacidad en dólares.

## Qué ML/datos usar en ibtrader y qué no

Contexto: ETFs diarios, universo pequeño → ~5.000 observaciones por activo, sin panel ancho. Toda la evidencia positiva de ML viene de paneles de miles de activos o de miles de millones de ticks, con rotaciones de 120 %/mes a 190 %/día que un individuo no paga.

**Usar (evidencia de décadas, barato, pocos parámetros):**
1. **Momentum de series de tiempo** como columna vertebral: señal 1/3/12 meses equiponderada (AQR: Sharpe neto 0.77 en 134 años, 0.62 en 2000–2013). Aceptar drawdowns de −25 % y recuperaciones de 2–6 años.
2. **Paridad de riesgo / vol targeting** como asignación base.
3. **Benchmark obligatorio**: TSMOM + paridad de riesgo con costos reales. Cualquier modelo debe batirlo fuera de muestra con *walk-forward anclado* (sin CV barajada), Sharpe deflacionado y umbral t > 3. Si la mejora de Sharpe es < 0.1–0.2, es ruido.
4. **Features con sentido económico y pocas**: retornos pasados a varios horizontes, volatilidad realizada, carry, spread de valor relativo entre ETFs. Son los predictores dominantes en GKX.
5. **Modelos someros, si acaso**: árboles con 1–5 niveles o boosting con pocas rondas, para *escalar* la posición (régimen de volatilidad), no para predecir el signo. HMM de 2 estados como filtro de riesgo, no como alfa.

**Descartar:**
- Redes profundas/LSTM sobre precios diarios: ventaja nula desde 2010 incluso con 500 acciones.
- Predicción puntual del precio o del signo diario: R² realista ≈ 0.01–0.02 %.
- Meta-labeling y "virtud de la complejidad": sin evidencia independiente.
- LLM sobre titulares: muere con 20 pb de costo, rota 190 %/día y se agotó en 30 meses.
- Alt-data institucional: $56–80 k por dataset, alfa concentrada en 3 días del reporte de empresas individuales — irrelevante para ETFs.
- Cross-sectional ML tipo GKX: el retorno vive en microcaps y distress.

**Cómo medir si el ML aporta**: misma ventana walk-forward para reglas y modelo; reportar Sharpe neto, rotación, drawdown y meses de recuperación; exigir que gane en al menos 2 de 3 subperiodos y descontar el Sharpe por el número de variantes probadas.

## Fuentes

- (P) Neudata, 23-feb-2026: https://www.neudata.co/press-release/ai-adoption-is-rising-but-alt-data-vendor-spend-hasn-t-neudata-report-finds
- (S) Hedgeweek 19-sep-2024: https://www.hedgeweek.com/hedge-funds-gear-up-for-a-2025-alternative-dataset-budget-boom/
- (P) Lowenstein Sandler, Alternative Data Report 2025: https://www.lowenstein.com/media/jujd45bp/alt-data-report-2025_final.pdf
- (P) Gu, Kelly, Xiu, RFS 2020: https://dachxiu.chicagobooth.edu/download/ML.pdf
- (P) Kelly, Malamud, Zhou (CEPR DP17194): https://repec.cepr.org/repec/cpr/ceprdp/DP17194.pdf
- (P) Kelly & Malamud, AQR jul-2025: https://www.aqr.com/insights/research/working-paper/understanding-the-virtue-of-complexity
- (S) CUHK sobre Avramov, Cheng, Metzker: https://cbk.bschool.cuhk.edu.hk/the-limitations-of-using-ai-to-pick-stocks/
- (P) Lopez-Lira & Tang, arXiv v6 (28-oct-2025): https://arxiv.org/html/2304.07619v6
- (P) Fischer & Krauss 2017: https://www.econstor.eu/bitstream/10419/157808/1/886576210.pdf
- (P) Sirignano & Cont 2018: https://arxiv.org/abs/1803.06917
- (P) Nystrup, DTU 2014: https://www2.imm.dtu.dk/pubdb/pubs/6808-full.html
- (P) arXiv 2605.27848 (HMM SPY/TLT/GLD): https://arxiv.org/abs/2605.27848
- (S) Quantpedia sobre Chague et al.: https://quantpedia.com/retail-day-trading-is-an-uphill-battle/
- (P) Barber & Odean 2000: https://faculty.haas.berkeley.edu/odean/Papers%20current%20versions/Individual_Investor_Performance_Final.pdf
- (P) McLean & Pontiff, JF 2016: https://www.gwern.net/doc/economics/2016-mclean.pdf
- (P) Jensen, Kelly, Pedersen, JF 2023: https://research-api.cbs.dk/ws/portalfiles/portal/95651880/theis_ingerslev_jensen_et_al_is_there_a_replication_crisis_in_finance_publishersversion.pdf
- (S) CXO sobre Harvey, Liu, Zhu: https://www.cxoadvisory.com/big-ideas/taming-the-factor-zoo/
- (P) Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following": https://www.TrendFollowing.com/whitepaper/Century_Evidence_Trend_Following.pdf
- (P) Moskowitz, Ooi, Pedersen, "Time Series Momentum": https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- (S) etf.com sobre Frazzini, Israel, Moskowitz: https://www.etf.com/sections/index-investor-corner/swedroe-trading-cost-truths
- (P) Israel, Laursen, Richardson, AQR/JPM 2021: https://www.aqr.com/Insights/Research/Journal-Article/Is-Systematic-Value-Investing-Dead
- (S) CFA Institute sobre Ilmanen: https://blogs.cfainstitute.org/investor/2017/01/03/count-on-low-expected-returns-says-antti-ilmanen/
- (P) Katona et al., JFQA 2025: https://ideas.repec.org/a/cup/jfinqa/v60y2025i2p551-579_1.html
- (P) Froot, Kang, Ozik, Sadka, NBER w22366: https://www.nber.org/papers/w22366
- (S) Risk.net: https://www.risk.net/ja/node/6374426
- (P) S&P DJI, SPIVA U.S. fin-2025: https://www.spglobal.com/spdji/en/spiva/article/spiva-us-year-end-2025/ · Persistence Scorecard: https://www.spglobal.com/spdji/en/documents/spiva/persistence-scorecard-year-end-2025.pdf
- (S) Quantpedia sobre Bailey et al. / Quantopian: https://quantpedia.com/quantopians-academic-paper-about-in-vs-out-of-sample-performance-of-trading-alg/
- (S) Hudson & Thames, meta-labeling: https://hudsonthames.org/?p=3448
