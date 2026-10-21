# Cómo generan sus algoritmos los fondos cuantitativos gigantes, y qué de eso cabe en ibtrader

**Fecha:** 21-10-2026 · **Método:** siete agentes de investigación en paralelo (fábrica de alphas, validación, portafolio y riesgo, ejecución e IBKR, infraestructura, datos alternativos y ML, sistemas abiertos completos), ~190 búsquedas y ~150 fuentes leídas completas, papers extraídos de PDF. Cada anexo en [`quant-funds-2026-10-21/`](quant-funds-2026-10-21/) trae los datos con fuente, fecha y marca primaria/secundaria. Las cifras que mueven decisiones tienen dos fuentes o están marcadas como sin confirmar.

## Respuesta corta

Los fondos gigantes no ganan por un algoritmo genial: ganan por un **proceso industrial** que un individuo sí puede copiar en su disciplina, aunque no en su escala. Las piezas que se repiten en todas las fuentes primarias son cinco: muchas señales débiles y poco correlacionadas (WorldQuant exige correlación < 0,7 con lo que ya tienen), validación brutal (t ≥ 3, PBO ≤ 0,05, Sharpe deflacionado por el número de pruebas, hold-out congelado), riesgo como parámetro ex ante (Millennium: −5 % y te recortan a la mitad), costos medidos en puntos básicos con fills propios, y datos point-in-time con hora de recepción.

Lo que un individuo con IBKR y Python **no** puede replicar: alphas rápidos (la ley C ~ 1/T de WorldQuant condena a retail por costos), datos alternativos ($56–80 k por dataset), apalancamiento tipo Medallion y la escala de búsqueda (millones de alphas). Lo que **sí** tiene evidencia de décadas y es barato: tendencia 1/3/12 meses + paridad de riesgo + vol target 10 % sobre ~10 ETFs, con **Sharpe neto realista 0,5–0,8 y drawdowns de 15–25 %**. Robert Carver, ex Man AHL, lleva 12 años operando exactamente eso con IBKR en código abierto (pysystemtrade): Sharpe 0,80 en vivo contra 1,29 de su propio backtest.

`ibtrader` ya tiene más validación estadística que cualquier framework abierto (walk-forward, CPCV-lite, DSR, PBO, gates estrictos, registro con hashes). Lo que le falta para ser "pesado" de verdad no es más ML: es la capa de datos PIT, el grafo de stages de pysystemtrade (forecast → escala → combinación → vol targeting → buffers), un modelo de costos calibrado contra los 2,5–4 pb reales de IBKR, golden files en CI y el bucle de producción con reconciliación. El plan por fases está al final. Y la regla honesta: si al terminar la fase 2 nada le gana al 60/40 con gates estrictos y periodo de confirmación congelado, la respuesta es indexar.

## Hallazgos

### 1. Cómo producen señales los fondos (anexo 1)

- **WorldQuant** industrializa la búsqueda: ~4 millones de alphas en 2017, meta de 100 millones, 400.000+ campos de datos en BRAIN (2026). Un alpha es una fórmula que da un peso diario por acción; los 101 publicados tienen tenencia 0,6–6,4 días y correlación media 15,9 % entre sí [Kakushadze 2016, primaria]. La ley empírica de sus 4.000 alphas reales: **centavos por acción ~ 1/turnover** — cuanto más rápido el alpha, menos gana por acción, así que solo sobrevive con costos ínfimos [Kakushadze & Tulchinsky 2015, primaria]. Nadie publica cómo combinan; lo documentado es el filtro: Sharpe > 1,25, turnover 1–70 %, correlación < 0,7 con el pool [secundarias concordantes].
- **Millennium** define el diseño desde el riesgo: −5 % del capital asignado → recorte a la mitad; −2,5 % adicional → despido [WSJ vía eFinancialCareers, dic-2025]. Eso empuja a estrategias de alto Sharpe, baja vol, neutrales a factor y de horizonte corto.
- **Medallion**: lo documentado por el Senado (2014) son 60 basket options con >129 millones de operaciones en un año, posiciones de "minutos o segundos", ejecución en ~1 ms y 90 % prestado por el banco. Lo de Zuckerman: un único modelo monolítico donde cada señal nueva se prueba contra sus costos; 51 % de aciertos. Los múltiplos de apalancamiento que circulan no tienen fuente primaria.
- **Man AHL** (primaria, 2023): sus modelos de tendencia son cruces de medias exponenciales a 5 velocidades (4–24 semanas) con 25 % de riesgo por clase de activo; después de costos, las velocidades rápidas pierden Sharpe. Llevan 30 años con la mayor asignación. **Jane Street** guarda cada dato "con la hora en que lo recibimos" para reconstruir qué sabían cuándo.
- **Ángulo contrario**: 33–50 % de los 296 factores publicados probablemente falsos [Harvey-Liu-Zhu 2016] frente a 82 % de réplica [Jensen-Kelly-Pedersen 2023]; el retorno post-publicación cae 58 % [McLean-Pontiff 2016]. Lo compatible: los factores existen, pero rinden la mitad de lo que dice el backtest.

### 2. Validación y control del overfitting (anexo 2)

- "Backtesting is not a research tool"; ~20 iteraciones bastan para descubrir una estrategia falsa al 5 % [López de Prado 2018, primaria]. Purga y embargo (h ≈ 1 % de T), CPCV con C(N,k) caminos, **PBO: rechazar si > 0,05** con S = 16 sobre ≥ 4 años diarios [Bailey et al. 2014, primaria]. DSR: el Sharpe esperado por azar con N pruebas, fórmula en el anexo.
- **t = Sharpe × √años ≥ 3** [Harvey-Liu-Zhu]; el haircut del 50 % es un error: con Sharpe < 0,4 el haircut pasa de 50 %, con > 1,0 es ≤ 25 % [Harvey & Liu 2015, primaria]. "No hay OOS verdadero con datos históricos, salvo el trading en vivo" [Arnott-Harvey-Markowitz 2019].
- **Práctica real de Man AHL** (primaria, 2015): la partición de datos se escribe antes; guardan registro de lo que prueban; todo se opera primero con capital propio 2–3 meses para cazar errores, no para significancia; esperan ~0,8× el Sharpe del backtest.
- Presupuesto de pruebas (cálculo propio con la fórmula de LdP): con 5 años de datos ≤ 45 configuraciones; con 10 años ~200. Con 10 años diarios el Sharpe observado debe superar ~1,0 / 1,3 / 1,55 para N = 10 / 100 / 1.000 pruebas.

### 3. Portafolio, sizing y riesgo (anexo 3)

- **Paridad de riesgo**: All Weather opera a 10 % de vol (memo de Bridgewater, mar-2020, primaria); −22 % en 2022 vs −16 % del 60/40; por debajo del 60/40 cada año desde 2019 [Fortune 2024]. AQR reporta SR 0,53–0,74 bruto sin financiamiento [2012, 2013]; con costos, el 60/40 la bate [Anderson et al. 2012]. Funciona como diversificador, no como milagro.
- **Vol targeting al 10 %**: mejora Sharpe en acciones (0,40 → 0,48–0,51) y recorta la cola izquierda; efecto nulo en bonos y commodities [Harvey et al. 2018]; en tiempo real solo sobrevive en momentum, ROE y BAB [Cederburg et al. 2020]. Carver: en tendencia sobre 37 futuros, SR 0,92 con vol targeting vs 0,57 sin.
- **Tendencia**: señales 1/3/12 meses, 67 mercados desde 1880, positivo neto en cada década, Sharpe por mercado ≈ 0,4 bruto, diversificado ≈ 0,76 neto [Hurst-Ooi-Pedersen 2017]; SG Trend +27,4 % en 2022 y −20,4 % may-24→may-25. **Salir por drawdown destruye valor**: IR 0,52 → 0,30/0,09/0,03 con stops a −15/−10/−5 % [Graham Capital 2022, primaria].
- **Sizing**: Kelly completo da 50 % de probabilidad de perder la mitad; usar 0,25–0,5 Kelly [Thorp 2006]. Carver: nunca más de medio Kelly, aplicar 0,75× al Sharpe del backtest, costos ≤ 1/3 del Sharpe bruto. Markowitz sin regularizar necesita ~3.000 meses de datos para 25 activos [DeMiguel et al. 2009]: usar inverse-vol o HRP.
- **Límites operativos** (solo secundarias): −5 % recorte, −7,5/−10 % liquidación. Lo que ibtrader ya trae (diaria 5 %, acumulada 20 %, drawdown 20 %) es más laxo que un pod y adecuado para un individuo.

### 4. Ejecución, costos e IBKR (anexo 4)

- **Impacto**: ley de raíz cuadrada `Y·σ·√(Q/V)` con Y de orden 1 [Tóth 2011]; Almgren 2005 estima exponente 0,6; por debajo de 0,3 % del volumen diario el impacto es lineal y menor [Bucci 2018]. Para órdenes de $1.000–10.000 en ETFs líquidos: **despreciable** (< 1,5 pb).
- **El calibrador real**: IBKR reporta para sus clientes Pro un costo total de ejecución y liquidación de **4,0 pb (julio 2026) y 2,5 pb (12 meses)** vs VWAP, trade medio $23.449 [IBKR, 3-ago-2026, primaria]. AQR, con $1,7 billones de fills: 13 pb de implementation shortfall; la variable que más explica es √(fracción del ADV).
- **Lo que de verdad cuesta a escala pequeña**: el mínimo de $1 por orden de IBKR Fixed = 10 pb en una orden de $1.000; rebalancear 10 ETFs al mes con órdenes de $1.000 ≈ 12 pb/orden ≈ 0,29 %/año; diario con 5 % de rotación ≈ 1,5 %/año. Con órdenes ≥ $5.000 baja a ~4 pb. Rebalanceo por umbral reduce el arrastre de 6,2 % a 0,5 %/año en un GTAA diario [SigTech vía Quantpedia 2022].
- **IBKR hoy (21-10-2026)**: Fixed 0,005/acc, mín. $1, máx. 1 %; Tiered desde 0,0035 con mín. $0,35; SEC 0,2 pb sobre ventas; TAF en pausa hasta dic-2026. API: 50 req/s, tercera violación cierra la sesión; algos Adaptive/VWAP/TWAP/PctVol solo en horario regular; hay que desactivar "Read-Only API" o las órdenes no llegan sin error; paper llena desde el tope del libro y no soporta VWAP ni Pegged. `ib_async` 2.1.0 (dic-2025), 102 issues abiertos, uno de oct-2026 con una orden incancelable ligada a un clientId muerto.
- **Reglas**: la regla PDT de $25.000 desaparece (FINRA 26-10, efectivo 4-jun-2026, implementación hasta oct-2027; sin fecha de IBKR). Residente de México: W-8BEN, retención 10 % en dividendos por tratado, 30 % sin él; T+1 desde may-2024.

### 5. Infraestructura y stack abierto (anexo 5)

- Piezas comunes en Man (ArcticDB, versionado y point-in-time), Two Sigma (as-of joins, pipelines end-to-end "lo más desatendido"), Jane Street (paridad numérica research→producción), AQR (modelo de costos calibrado con fills propios), Cubist (mismo motor para simulación y live).
- **Datos PIT**: Compustat se re-estandariza en cada vintage y eso mete look-ahead; replicar sin snapshot es "casi imposible" [Lyle-Siano-Yohn 2024]. Precios para un individuo (oficiales, 21-10-2026): Massive (ex-Polygon) $29/mes 5 años; Tiingo Power $30/mes 30+ años EOD; EODHD $19,99–$99,99; Databento $199/mes. yfinance: solo supervivientes, ajustes retroactivos, sin SLA.
- **Frameworks**: Lean (Apache, IBKR sí, pero CLI local exige organización de pago), nautilus_trader (Rust, IBKR "stable" con 189 issues, 2.0 quita Python 3.12), vectorbt PRO ($25/mes, OSS congelado), Qlib (MIT, research completo con MLflow, sin ejecución), **pysystemtrade** (GPL, producción real en IBKR desde 2014, pandas 2.1.3 fijado), skfolio (BSD, CPCV sklearn, activa), mlfinlab (cerrada, de pago), backtrader (abandonado). Ninguno hace lo que `research/` de ibtrader hace en validación.
- Brecha backtest→live documentada por QuantConnect y Nautilus: fills instantáneos, límites que se llenan al tocar el precio, impacto no modelado, estado no determinista tras reinicios.

### 6. Datos alternativos y ML (anexo 6)

- Alt-data: $2,8 bn de gasto en 2025, ≈20 clientes por dataset, $56–80 k por dataset [Neudata 2026, Hedgeweek 2024]. La alfa documentada (satélite: 4–5 % en 3 días alrededor del reporte) es de acciones individuales y se concentra en el anuncio: irrelevante para ETFs.
- **ML con evidencia**: en 30.000 acciones y 920 features, el mejor modelo (NN3) logra **0,40 % de R² mensual**; árboles y boosting 0,33–0,34 %; el deep learning "tiene beneficios limitados"; rotación 120–150 %/mes [Gu-Kelly-Xiu 2020, primaria]. El retorno cae 62–80 % sin microcaps y distress [Avramov et al. 2023]. LSTM sobre S&P 500: ventaja cero desde 2010 [Fischer-Krauss 2017]. GPT-4 sobre titulares: Sharpe 2,97 bruto que muere con 20 pb de costo y decayó de 6,5 a 1,2 en 30 meses [Lopez-Lira & Tang 2025].
- **Lo que sí**: tendencia 1/3/12 meses (Sharpe neto 0,77 en 134 años [AQR]), paridad de riesgo, features económicas y pocas (retornos a varios horizontes, vol realizada, carry), modelos someros solo para escalar la posición. Un ETF diario tiene ~5.000 observaciones: cualquier modelo profundo es overfitting.
- 97 % de los day traders persistentes de Brasil perdieron [Chague et al. 2019]; 79 % de fondos large-cap activos perdieron contra el S&P en 2025 [SPIVA].

### 7. Sistemas abiertos completos con resultados reales (anexo 7)

- **Carver / pysystemtrade** (primaria): 12 años en IBKR; Sharpe 0,80 (rf = 0) vs 0,52 de AHL y 0,54 del SG CTA; peor año −16,3 % (2024-25), mejor +23,7 % (2025-26); vol objetivo 25 %; costos 85–88 pb/año (slippage 55 + comisiones 33); sin su algo de ejecución el slippage sería 134 pb. Backtest de su sistema: Sharpe 1,29 → vivo 0,80: **brecha ≈ 0,5 aun en el autor más riguroso**. Pipeline: forecast crudo → escalado a |10| con tope ±20 → combinación con FDM → vol targeting → pesos × IDM → buffers de ±10 % → ejecución pasiva que se vuelve agresiva. Fórmulas exactas en el anexo.
- **Clenow**: "trend following estándar sobre acciones pierde"; momentum long-only con filtro de índice; sin track record público. **Chan**: sus propias señales se rompieron (insiders 2014-15, buy-on-gap tras 2013); "quedan obsoletas muy rápido".
- **Quantopian**: 888 algos, R² de 0,02 entre Sharpe in-sample y OOS; más días de backtest → peor OOS [Wiecki et al. 2016]; cerró en 2020 porque la estrategia market-neutral no daba resultados. **QuantConnect Alpha Streams** cerró en 2022: incluso el top 5 % perdió contra el S&P 500 y las alphas no correlacionadas "no fueron aditivas".
- CTAs 1994-2007: exceso neto 85 pb/año, no significativo; corregir supervivencia baja el retorno de 12,6 % a 4,9 % [Bhardwaj-Gorton-Rouwenhorst, NBER].

## Contradicciones y huecos

- **Decaimiento**: −58 % post-publicación [McLean-Pontiff] vs −12 % corregido [Chen-Zimmermann] vs 82 % de réplica [JKP] vs "la mayoría falsa" [HLZ]. Usar la regla conservadora: el backtest rinde la mitad.
- **Vol targeting**: +25 % de Sharpe [Moreira-Muir] vs peor en 72 de 103 estrategias en tiempo real [Cederburg]. Solo aplicarlo a activos de riesgo y a tendencia.
- **Impacto**: exponente 0,5 vs 0,6 vs lineal a escala pequeña; a la escala de un individuo no importa.
- **Límites de pods** (5 %/7,5 %/10 %): todas las cifras son de Substacks; cero disclosure primaria.
- **Carver**: shadow cost 250 en el blog vs 50 en `defaults.yaml`; 2025 tabulado como −14,7 % y −15,4 %.
- **Sin fuente primaria**: "99 % de los algos de Quantopian sin edge", supervivencia en Collective2/Darwinex, entidad de IBKR que atiende a México, precio de Sharadar, cifras de Virtu/Abel Noser, protocolo interno de Two Sigma.
- El presupuesto de búsqueda web se agotó en todos los agentes; SSRN, NBER, IBKR (403) y S&P (SPIVA) bloquearon fetches; se usaron PDF espejo y páginas bajadas con curl.

## Qué verificar antes de decidir

1. **Tus cuatro datos**, que siguen sin respuesta y mandan sobre el sizing: drawdown máximo que toleras, capital inicial, horizonte en años, si la cuenta IBKR ya existe. Con capital < $25.000 el mínimo de $1 por orden obliga a rebalanceo mensual por umbral; con < $10.000 ni eso.
2. **Entidad y fiscalidad de IBKR para México**: confirmar en tu cuenta qué entidad te atiende, que el W-8BEN está vigente (año de firma + 3) y cómo acreditas el 10 % retenido contra el ISR.
3. **Margen**: para vol target 10 % con paridad de riesgo hace falta ~1,5× de apalancamiento; verificar la tasa de margen vigente de IBKR y si prefieres aceptar 5–6 % de vol sin apalancar.
4. **Proveedor de datos**: Tiingo Power ($30) o Massive Starter ($29) sustituyen a yfinance; decidir antes de la fase 1 porque el hash del dataset depende de ello.
5. **Cuándo migra IBKR la regla PDT**: hoy opera con la regla vieja hasta que lo anuncie.

## Arquitectura objetivo para ibtrader ("super pesada" sin reescribir)

Lo que ya existe y se queda: `backtest/engine` (con `restricted` por barra desde hoy), `validation/walkforward`, `research/{cpcv,pbo,dsr,gates,registry,suite}`, `risk/{manager,state_machine}`, `ops/{journal,killswitch,artifacts}`, `broker/{ibkr,simulated}`, `strategy/{tsmom,rotation,sma_crossover,mean_reversion}`, `portfolio/sizing` (vol target, risk parity), `regime/gmm`, `ml/cv` (purged split). Es la parte que los frameworks abiertos no tienen.

Lo que se añade, por capa, con la fuente de cada idea:

| Capa | Componente nuevo | De dónde viene | Módulo |
|---|---|---|---|
| Datos | Parquet por `vintage_date` + manifiesto SHA-256 por archivo; universo con delistings; rechazo de timestamps futuros y `max_price_spike` | ArcticDB, Qlib PIT, pysystemtrade, Jane Street | `data/lineage`, `data/validators`, `data/providers` (Tiingo/Massive) |
| Señales | Grafo de stages cacheado: `rawdata → forecast → scale/cap → combine → size → portfolio → accounts`; forecasts escalados a \|10\| con tope ±20; FDM/IDM con `dm_max 2.5`; `date_method: expanding` obligatorio | pysystemtrade (fórmulas en anexo 7) | `strategy/`, nuevo `pipeline/` |
| Reglas | EWMAC a 4–6 velocidades (16/64 … 64/256), señal 1/3/12 meses, breakout; carry solo si hay proxy (dividend yield / curva) | Man AHL, Hurst-Ooi-Pedersen, Carver | `strategy/tsmom`, `strategy/ewmac` |
| Cartera | Núcleo risk parity por cajas (acciones, Treasuries intermedios y largos, TIPS, oro, commodities, REIT, cash), pesos inverse-vol o HRP, vol target 10 %, tope 1,5×, buffers ±10 %, `long_only_instruments` | Bridgewater, López de Prado 2016, Harvey 2018, Carver | `portfolio/sizing`, nuevo `portfolio/buffering` |
| Validación | Registro con N de pruebas y presupuesto (años ≥ 2·ln N / SR²); hold-out congelado declarado en config y bloqueado por `gates`; PBO ≤ 0,05 con S = 16; DSR ≥ 0,95; t ≥ 3; strict gates ya exigen ganar al B&H | LdP, Bailey, Harvey-Liu, Man AHL | `research/registry`, `research/gates`, `research/suite` |
| Costos | `commission_fixed/tiered + reg_fees + half_spread + Y·σ·√(Q/V)`; sanidad: media por orden ≥ 2,5–4 pb; arrastre anual y turnover en todo reporte; rebalanceo por umbral | IBKR 2026, Tóth, Almgren, AQR | `backtest/engine`, `research/cost_stress` |
| CI | Golden files por estrategia: `expected_statistics.json` (Sharpe, órdenes, drawdown, hash de órdenes) sobre fixtures; regenerar solo con commit explícito | Lean | `tests/golden/` |
| Ejecución | Simulador con `prob_fill_on_limit`, latencia, slippage en ticks; algo pasivo→agresivo (`algoOriginalBest`); ledger de slippage real (precio/hora de decisión vs fill); solo horario regular; nunca VWAP en paper | Nautilus, pysystemtrade, IBKR docs | `broker/simulated`, `execution/`, nuevo `ops/slippage_ledger` |
| Producción | `run_systems` → posiciones óptimas con buffers → pila instrumento/broker en SQLite → `stack_handler` con `ib_async` → reconciliación diaria con IB y curva live vs OOS; IBC para el reinicio diario del Gateway; kill switch y `halt_next_day` ya fail-closed | pysystemtrade, QuantConnect reconciliation | `ops/status`, nuevo `ops/stack` |
| Benchmarks | AOR (60/40), RPAR (All Weather en ETFs), SG Trend; carteras aleatorias (Clenow) | anexos 3 y 7 | `research/report` |

Universo propuesto (10 + cash): SPY o VTI, VEA, VWO, IEF, TLT, TIP, GLD, PDBC o DBC, VNQ, más BIL/SGOV como cash. Todos con spread ≤ 2 pb y ADV de miles de millones, salvo PDBC y TIP (≤ 5 pb).

## Plan por fases

**Fase 0 — hecha hoy.** Hardening fase 1 en `main` (gates estrictos deciden el PASS, `restricted_bar_frac` real, hashes obligatorios, riesgo fail-closed, CI en ubuntu + macOS).

**Fase 1 — cimientos (2 semanas).** Proveedor de datos con delistings y manifiesto PIT; modelo de costos de IBKR con las reglas de sanidad; golden files en CI para SMA, TSMOM y rotación; registro de experimentos con N, presupuesto de pruebas y hold-out congelado (últimos 2 años) bloqueado por `gates`. Definición de hecho: un `research-run` sobre fixtures reporta arrastre anual, turnover, N y DSR, y falla si toca el hold-out.

**Fase 2 — el sistema pesado (4 semanas).** Grafo de stages con forecasts escalados, FDM/IDM, vol target 10 %, buffers ±10 % y `long_only`; reglas EWMAC multi-velocidad + 1/3/12 meses sobre el universo de 10 ETFs; núcleo risk parity por cajas con HRP; benchmarks AOR, RPAR, SG Trend y 1.000 carteras aleatorias; validación completa (CPCV, PBO ≤ 0,05, DSR ≥ 0,95, t ≥ 3, ganar al 60/40 ajustado por riesgo). Una sola apertura del hold-out al final. Definición de hecho: informe honesto con veredicto; si FAIL, la recomendación escrita es indexar y el proyecto se queda como laboratorio.

**Fase 3 — paper disciplinado (3 meses de calendario, 2 semanas de código).** Simulador con fills probabilísticos; algo pasivo→agresivo con `ib_async`; ledger de slippage; reconciliación diaria; IBC y reinicio del Gateway; alertas. Operar en paper con la configuración congelada; matar si el drawdown es inconsistente con el Sharpe asumido (Man AHL); **no retocar con resultados en vivo**. Esperar 0,75× el Sharpe del backtest.

**Fase 4 — capital real, pequeño (solo si fase 3 pasa).** Tamaño mínimo que mantenga órdenes ≥ $5.000; límites: −20 % desde máximo → vol target a 5 %; −30 % → parar y revisar; revisión anual, no mensual. Opcionales después: HMM de 2 estados como filtro de vol (no como alfa), skfolio para CPCV, BRAIN de WorldQuant como laboratorio de alphas transversales, nautilus_trader 2.0 cuando salga la final.

Lo que **no** entra en ningún plan: redes profundas sobre precios diarios, LLM sobre titulares, alt-data de pago, ETFs apalancados, señales intradía, optimización de Markowitz sin regularizar, y cualquier cambio de parámetros motivado por el último mes.

## Fuentes

Las 150 fuentes con enlace, fecha y marca primaria/secundaria están en los siete anexos:

- [01 — Fábrica de alphas](quant-funds-2026-10-21/01-fabrica-de-alphas.md): WorldQuant (arXiv 1601.00991, 1509.08110), Senado EE. UU. 2014 sobre Medallion, Two Sigma, Jane Street, AQR, Man AHL *Need for Speed*, Harvey-Liu-Zhu, McLean-Pontiff, Khandani-Lo.
- [02 — Validación](quant-funds-2026-10-21/02-validacion-anti-overfitting.md): Bailey-Borwein-LdP-Zhu (PBO), LdP *10 Reasons*, Harvey & Liu *Backtesting* y *Evaluating Trading Strategies*, Arnott-Harvey-Markowitz, Man AHL 2015, Jensen-Kelly-Pedersen, skfolio.
- [03 — Portafolio y riesgo](quant-funds-2026-10-21/03-portafolio-sizing-riesgo.md): Bridgewater All Weather y memo 2020, AQR 2012/2013, Moreira-Muir, Cederburg et al., Moskowitz-Ooi-Pedersen, Hurst-Ooi-Pedersen, Thorp 2006, Gârleanu-Pedersen, DeMiguel et al., Graham Capital, ECB 2020.
- [04 — Ejecución e IBKR](quant-funds-2026-10-21/04-ejecucion-costos-ibkr.md): Almgren-Chriss, Almgren et al. 2005, Tóth, Zarinelli, Bucci, Frazzini-Israel-Moskowitz, IBKR (comisiones, datos, API, paper, métricas jul-2026), FINRA 26-10, SEC, IRS, ib_async.
- [05 — Infraestructura](quant-funds-2026-10-21/05-infraestructura-y-stack-abierto.md): ArcticDB, Flint, Jane Street podcast, Lyle-Siano-Yohn, Qlib, Lean, nautilus_trader, pysystemtrade, skfolio, precios de Massive/Tiingo/EODHD/Databento.
- [06 — Datos alternativos y ML](quant-funds-2026-10-21/06-datos-alternativos-y-ml.md): Neudata, Lowenstein, Gu-Kelly-Xiu, Kelly-Malamud-Zhou, Lopez-Lira & Tang, Fischer-Krauss, Chague et al., Barber-Odean, SPIVA 2025.
- [07 — Sistemas completos](quant-funds-2026-10-21/07-sistemas-completos-carver-clenow-chan.md): Carver (blog y pysystemtrade), Clenow, Chan, Wiecki et al. 2016, QuantConnect Alpha Streams, BTOP50, Bhardwaj-Gorton-Rouwenhorst, FINRA 09-31.
