# Anexo 5 — Infraestructura de research y producción, y el stack abierto que la imita

Reporte del agente de investigación (21-10-2026). 24 búsquedas y 30+ lecturas completas (READMEs, docs, releases, podcast, paper). [P]=primaria, [S]=secundaria.

## Hallazgos

### 1. Qué publican los fondos sobre su infraestructura

**Man Group.** ArcticDB es una "serverless DataFrame database" C++ con API pandas; versionado nativo ("travel back in time", snapshots), backends S3/LMDB/Azure, wheels para Python 3.9–3.14. Licencia **BSL 1.1**: cada versión pasa a Apache 2.0 en una fecha (v1.0→16-03-2025 … v6.21→04-08-2028); "users may not use ArcticDB for production use" sin acuerdo con Man [README, P]. Última release v6.28.1. Casos de uso internos: "deep tick history analysis", "point-in-time analysis of research datasets", backtesting de señales, trading automatizado casi en tiempo real; Arctic original desde 2012 [comunicado con Bloomberg, 27-02-2023, P].

**Two Sigma.** Flint (25-10-2018, P): librería de series temporales sobre Spark con *as-of join* (`LeftJoin` hacia atrás, `FutureLeftJoin` hacia adelante), `summarizeWindows`, `summarizeCycles`. El CTO describe un "data pipeline ecosystem" (Crux para ETL/calidad, Liberty para workflow/entity mapping) y afirma que "the part of the data world that is most underserved is end-to-end pipelining" [S]. La investigación vive en JupyterLab [S].

**Jane Street.** Podcast *Signals & Threads* ep. 5 (2020, P): mitad del tiempo en Python "mostly for research purposes", OCaml para "production critical development". Para pasar un modelo a producción exportan pesos entrenados y valores de muestra y verifican "the exact same results". Si no puedes "restart from scratch and rereach the same conclusion", es un problema.

**AQR.** "Trading Costs" (Frazzini, Israel, Moskowitz; 2018, P): $1.7 trillion de ejecuciones reales, 21 mercados, 19 años; costes "an order of magnitude smaller than previous studies suggest"; un modelo calibrado por tamaño de orden, acción y tiempo supera a los demás fuera de muestra. Mensaje: calibra tu modelo de costes con tus propios fills.

**D.E. Shaw / Citadel Securities / Point72-Cubist** (ofertas de empleo, S): "Research Platform teams … research infrastructure that power large-scale simulations"; "productionize research workflows"; "trading and research infrastructure … for live trading and simulations", Python + kdb.

**Piezas comunes**: (a) almacén de datos versionado/point-in-time; (b) *as-of joins* como primitiva; (c) el mismo motor para simulación y live; (d) registro de experimentos; (e) reconciliación live-vs-OOS; (f) modelo de costes calibrado con fills reales; (g) verificación de paridad numérica research→producción.

### 2. Datos point-in-time y sesgos

- Lyle, Siano & Yohn, *Re-Standardized Financial Statement Data* (jul-2024, P): los productos comunes de Compustat se re-estandarizan en cada vintage, lo que "introduces a form of look-ahead bias"; "precise replication … is nearly impossible" sin Snapshot. Compustat PIT desde dic-1986 [S].
- Qlib implementa su propia base PIT: cada valor con `date` de publicación y `period`, y las revisiones coexisten [docs, P].
- QuantConnect US Equity Security Master: ~27.500 acciones, splits/dividendos/delistings desde 1998, pero "cannot be consumed another way" fuera de LEAN [P].

**Precios 2026 para un individuo** (páginas oficiales, 21-10-2026, P):

| Proveedor | Plan | Precio | Cobertura |
|---|---|---|---|
| Massive (ex-Polygon) | Basic / Starter / Developer / Advanced | $0 / $29 / $79 / $199 mes | 2 / 5 / 10 / 20+ años; Starter y Developer con 15 min de retraso; uso individual |
| Databento | Standard / Plus / Unlimited | $199/mes; $1.750 y $4.500/mes anual | 16+ años L0, 1 año L1 en Standard; $125 de crédito al registrarse |
| Tiingo | Starter / Power / Commercial | $0 / $30 mes / $50 mes | 30+ años EOD, 110.341 símbolos; fundamentales 15+ años en Power |
| EODHD | Free / EOD All-World / EOD+Intraday / Fundamentals / All-In-One | $0 / $19.99 / $29.99 / $59.99 / $99.99 mes | fundamentales en los planes altos |
| Sharadar (Nasdaq Data Link) | SF1/SEP | **precio no obtenido** | fundamentales desde 1990, precios desde 1998 [S] |

yfinance/Stooq: universo solo de supervivientes, precios ajustados retroactivamente, sin SLA (análisis del agente). ibtrader hoy depende de yfinance 1.x.

### 3. Stack abierto

| Proyecto | Cubre | Licencia | IBKR | Última release | Madurez |
|---|---|---|---|---|---|
| QuantConnect Lean | motor event-driven C#/Python, universos, corporate actions, live | Apache-2.0 | Sí (`lean live deploy`, IB Key, reinicio semanal, IBKR Pro); la CLI exige organización de pago | lean-cli 1.0.230 (15-oct-2026) | Alta; dependencia de Docker y datos QC |
| nautilus_trader | núcleo Rust, mismo código backtest/live | LGPL-3.0 | Adaptador "stable": ibapi 4.0.1, gateway dockerizado | 1.231.0 (02-08-2026); 2.0.0rc7 (15-10-2026) **quita Python 3.12**; "advises against RC for live trading" | Alta pero en transición; 189 issues IB |
| vectorbt OSS / PRO | vectorizado, sweeps masivos | Apache 2.0 + Commons Clause / privado | No ejecución | OSS "being maintained only"; PRO v2026.10.5, desde $25/mes, $500 lifetime; CV purgada y walk-forward | PRO activa; OSS congelada |
| zipline-reloaded | event-driven diario, Pipeline | Apache-2.0 | No | 3.2.0, Python 3.11–3.14, pandas <3; "maintained only for compatibility and critical bugs" | Mantenimiento |
| backtrader | event-driven | GPL-3.0 | IbPy (muerto) | 1.9.78.123 (19-04-2023) | Abandonado |
| Microsoft Qlib | datos→factores→modelos→backtest→registro MLflow→RL | MIT | No | v0.9.8; Python 3.8–3.12; dataset oficial "temporarily disabled" | Alta en research, nula en ejecución |
| pysystemtrade | sistema completo de futuros | GPL-3.0 | Sí, `ib_async>=2,<3` | v1.8.3, Python ≥3.10, **pandas==2.1.3, pymongo==3.11.3** | Producción real del autor desde 2014 |
| skfolio | optimización de cartera + CPCV/WalkForward sklearn | BSD-3 | No | v1.9.10 (21-10-2026), Python 3.10–3.14 | Activa |
| mlfinlab | CPCV, PBO, labeling | "all rights reserved", de pago | No | 1.3.0 (jul-2021) | Cerrada |
| alphalens/pyfolio-reloaded | análisis de factores / tearsheets | Apache | No | 0.4.2 (mar-2025) / 0.9.9 | Mantenimiento mínimo |

Arquitectura de pysystemtrade (docs, P): siete *stages* encadenados `rawdata → rules → forecastScaleCap → combForecast → positionSize → portfolio → accounts`, cada método cacheado; estimación con `date_method: expanding` ("recommended"), `in_sample` ("never!") o `rolling`. En producción: `run_systems` guarda *optimal positions* con buffers (ej. "entre +10.87 y +13.32 contratos"), precio y hora de referencia "so we can calculate the slippage"; tres pilas de órdenes (instrumento → contrato → broker) y `run_stack_handler`; detección de spikes; parámetros fijos en producción.

### 4. Reproducibilidad y disciplina

- **Qlib**: `MLflowExpManager` con `log_params/log_metrics/log_artifact`, plantillas `SignalRecord/SigAnaRecord/PortAnaRecord`; flujo `qrun` por YAML [P].
- **Lean**: cada algoritmo de regresión implementa `ExpectedStatistics` (Sharpe, Total Orders, `OrderListHash`), `DataPoints`; CI "Regression Tests" [P]. Son *golden files* literales.
- **pysystemtrade**: estado del backtest pickled por corrida; config YAML + `private_config.yaml` versionada aparte [P].
- **Jane Street**: exportar pesos + valores de muestra y comparar salida exacta entre runtimes [P].
- **Nautilus**: "deterministic event-driven architecture" y un solo código para backtest y live [P].

### 5. Ángulo contrario

- QuantConnect, *Reconciliation* (P): fills instantáneos vs ~0.5 s en vivo; límites se llenan "as soon as the limit price is touched"; impacto de mercado no modelado; revisiones de datos cambian backtests pasados.
- Nautilus *fill models* (P): "Historical data cannot show how a simulated order would have interacted with other market participants"; `prob_fill_on_limit=1.0` por defecto. Issues IB de oct-2026: stall silencioso de L2, ticks con `ts_init` = hora de recepción, barras perdidas, commission reports que rompen la reconciliación, "Duplicate order id" [P].
- hftbacktest (P): "begin trading with a small size and align the results first".
- pysystemtrade fija pandas 2.1.3 (incompatible con pandas 2.2.2 de ibtrader). Nautilus 2.x abandona Python 3.12.
- Realidad de un sistema casero: Carver, año uno SR 2.54 vs 0.88 de backtest ("brilliantly flukey"); desde inception 2014-2023 SR 0.58 vs benchmarks 0.43/0.38; costes vivos 90 pb vs ~1 % del backtest [qoppac, P].

## Contradicciones y huecos

1. ArcticDB "open source" en prensa vs BSL que prohíbe producción sin licencia. 2. Nautilus lista IB como "stable" mientras acumula 189 issues IB. 3. QuantConnect "open source" pero la CLI local exige organización de pago. 4. Qlib README dice Python ≤3.12 mientras el ecosistema migra a 3.13/3.14. 5. Huecos: precio de Sharadar; delisting de CRSP; blog de ingeniería de Citadel/D.E. Shaw.

## Arquitectura objetivo recomendada para ibtrader

Lo que hoy existe (`src/ibtrader`): `backtest/engine`, `validation/walkforward`, `research/{cpcv,pbo,dsr,gates,registry,cost_stress}`, `data/{cache,lineage,validators,universe}`, `broker/{ibkr,simulated}`, `risk/{manager,state_machine}`, `ops/{journal,killswitch}`. Es más de lo que tiene cualquier framework abierto en validación estadística; lo que falta es la capa de datos PIT, la disciplina de paridad y el bucle de producción. Orden propuesto, sin reescribir:

1. **Datos PIT versionados (ArcticDB/Qlib PIT/pysystemtrade).** Parquet particionado por `vintage_date` + manifiesto con hash SHA-256 por archivo en `data/lineage.py`; universo con delistings (sustituir yfinance por Massive Starter $29 o Tiingo Power $30; EODHD Fundamentals $59.99 o Sharadar para fundamentales). Validadores con `max_price_spike` y rechazo de timestamps futuros.
2. **Grafo de stages con caché (pysystemtrade).** Refactorizar en `rawdata → forecast → scale/cap → combine → size → portfolio → accounts`; `date_method: expanding` obligatorio para cualquier estimación; parámetros congelados para live.
3. **Registro de experimentos enriquecido (Qlib Recorder).** JSONL propio con `git_sha`, `config_hash`, `data_vintage_hash`, `seed`, `lockfile_hash`, artefactos y estado; *frozen hold-out* declarado en config y bloqueado por `research/gates.py`.
4. **CI de regresión con golden files (Lean).** Por estrategia, fixture + `expected_statistics.json` (Sharpe, órdenes, drawdown, hash de la lista de órdenes); se regenera solo con un commit explícito.
5. **Modelo de ejecución explícito (Nautilus + AQR).** En `broker/simulated`: `prob_fill_on_limit`, slippage en ticks, latencia, consumo de liquidez; *ledger* de slippage real (precio/hora de referencia al decidir vs fill) para recalibrar costes con fills propios.
6. **Bucle de producción (pysystemtrade).** `run_systems` → posiciones óptimas con buffers → pila instrumento/broker en SQLite → `stack_handler` con ib_async → reconciliación diaria con IB y curva live vs OOS en `ops/status`.
7. **Opcionales después.** skfolio para CPCV/portafolio (BSD, Python 3.12 OK); nautilus_trader 2.0 solo cuando salga la final; vectorbt PRO para sweeps masivos. Mantener propios: walk-forward, CPCV-lite, DSR, PBO, gates, máquina de estados de riesgo, kill switch.

## Fuentes

Primarias:
- https://github.com/man-group/ArcticDB · https://arcticdb.io/ · https://www.man.com/news-centre/man-group-brings-powerful-dataframe-database-product-arcticdb-to-market-with-bloomberg
- https://www.twosigma.com/articles/introducing-flint-a-time-series-library-for-apache-spark · https://www.twosigma.com/open-source/
- https://signalsandthreads.com/python-ocaml-and-machine-learning/
- https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs
- https://business.columbia.edu/sites/default/files-efs/imce-uploads/ADP/Fall%202024/Lyle%20Siano%20Yohn%202024.pdf
- https://qlib.readthedocs.io/en/latest/advanced/PIT.html · https://qlib.readthedocs.io/en/latest/component/recorder.html · https://github.com/microsoft/qlib/releases
- https://github.com/QuantConnect/Lean · https://github.com/QuantConnect/lean-cli/releases · https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages/interactive-brokers · https://www.quantconnect.com/docs/v2/our-platform/live-trading/reconciliation
- https://github.com/nautechsystems/nautilus_trader/releases · https://nautilustrader.io/docs/latest/integrations/interactive_brokers/ · https://nautilustrader.io/docs/nightly/concepts/backtesting/fill-models/
- https://github.com/pst-group/pysystemtrade · https://raw.githubusercontent.com/pst-group/pysystemtrade/refs/heads/develop/docs/production.md · https://raw.githubusercontent.com/pst-group/pysystemtrade/refs/heads/develop/docs/backtesting.md · https://qoppac.blogspot.com/search?q=performance+review
- https://github.com/stefan-jansen/zipline-reloaded/releases · https://github.com/mementum/backtrader · https://vectorbt.pro/ · https://github.com/skfolio/skfolio/releases · https://github.com/hudson-and-thames/mlfinlab
- https://massive.com/pricing · https://databento.com/pricing · https://www.tiingo.com/about/pricing · https://eodhd.com/pricing
- https://hftbacktest.readthedocs.io/en/latest/debugging_backtesting_and_live_discrepancies.html

Secundarias:
- https://ocaml.org/success-stories/large-scale-trading-system · https://venturebeat.com/business/two-sigma-acquires-hivemind-strengthens-data-driven-investing · https://www.citadelsecurities.com/careers/details/platform-engineer/ · https://job-boards.greenhouse.io/point72/jobs/7666604002
- https://quantrocket.com/sharadar · https://kenanflaglerresearchtools.web.unc.edu/research-resource/compustat-snapshot/
- https://snyk.io/advisor/python/backtrader · https://nexusfi.com/a/automation/backtest-to-live-performance-gap
