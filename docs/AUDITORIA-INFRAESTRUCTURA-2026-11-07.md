# Auditoría completa e infraestructura "institucional" para ibtrader

**Fecha:** 07-11-2026 · **Commit auditado:** `1c9868d` (el PC de Adam en `C:\dev\apps\IBKR-INVESTMENT-app` y `origin/main` están en el mismo commit, árbol limpio) · **Verificaciones:** `ruff`, `mypy` y `pytest` en verde en la nube sobre ese commit.

**Qué es este documento:** el estado real del sistema, módulo por módulo; qué sobra, qué falta y qué añadir; un diseño de infraestructura que copia de los fondos grandes lo que sí escala a una persona con capital modesto; cómo meter Claude por API sin convertirlo en un riesgo; y un plan priorizado. No repite el playbook del 21-10 (`docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md`), que sigue vigente: lo usa como base y dice qué de él está hecho, qué no y qué está mal.

---

## 0. Respuesta corta

1. **Un sistema "casi infalible" que dé "ganancias top mundial" no existe, y perseguirlo es la forma más rápida de perder capital.** La sección 1 explica el mecanismo. Lo alcanzable, con evidencia de décadas, es un retorno ajustado a riesgo algo mejor que el del índice: Sharpe neto de 0,5 a 0,8 con caídas máximas del 15 al 25 %.
2. **El código está más avanzado que su uso.** El motor de la fase 2 (grafo de señales, paridad de riesgo por cajas, HRP, vol target, buffers, gates estadísticos) existe y tiene tests. Pero **nunca se ha corrido sobre datos reales del universo de 10 ETF**: en el PC solo hay datos de SPY.
3. **El paper trading está congelado sobre la estrategia equivocada.** `data/paper_config_freeze.json` congela SMA 10/30 sobre SPY, la estrategia que el propio repo ya rechazó (CAGR 0,4 % contra 11,7 % del buy & hold). Además el reloj del paper está en el día 0: no hay `paper_account.json` ni `paper_equity.jsonl`.
4. **La ejecución automática está al 0 %.** `IBKRBroker` no se instancia en ningún sitio: ningún comando envía órdenes a IBKR, ni siquiera en paper. Sin órdenes reales en paper no hay fills ni slippage medido, así que la fase 3 del plan no mide lo que dice medir.
5. **Hay un falso positivo vivo en los gates.** El DSR no exige un mínimo de observaciones: la corrida `sim_research_smoke` dio DSR = 0,99997 con **24 observaciones** y el veredicto `INTERESTING_OWNER_PC_RERUN`.
6. **Claude sí cabe, pero fuera de la ruta de órdenes:** para explicar, revisar, auditar y hacer triage. No para generar señales. La puerta IA que ya existe (`intelligence/brief.py`) es el diseño correcto y hay que extenderla, no reemplazarla.

---

## 1. Lo que pides contra lo que es posible

### Términos (definidos antes de usarlos)

- **Retorno:** cambio porcentual del valor de la cartera en un periodo. **CAGR** es el retorno anual compuesto: la tasa constante que lleva del capital inicial al final.
- **Volatilidad (vol):** desviación estándar anualizada de los retornos diarios (σ diaria × √252). Mide cuánto oscila la cartera.
- **Retorno ajustado a riesgo / Sharpe:** (retorno anual − tasa libre de riesgo) ÷ volatilidad anual. Un Sharpe de 1 significa que ganas por encima del bono una vez tu volatilidad por año. El S&P 500 a largo plazo ronda 0,4–0,5.
- **Drawdown (DD):** caída desde el máximo previo de la cartera hasta el mínimo posterior. El **DD máximo** es la peor de todas.
- **Beta:** cuánto se mueve tu cartera por cada 1 % del mercado. **Alfa:** el retorno que sobra después de descontar lo que explica la beta. "Ganarle al mercado" de verdad es tener alfa positivo neto de costos.
- **In-sample (IS) / out-of-sample (OOS):** datos usados para elegir parámetros contra datos que el proceso nunca vio. Solo el OOS es evidencia.
- **Sobreajuste (overfitting):** elegir reglas o parámetros que explican el ruido del pasado. Se ve espectacular IS y falla OOS.
- **Punto básico (pb, bps):** 0,01 %. **Slippage:** diferencia entre el precio con el que decidiste y el precio al que realmente se ejecutó. **Turnover:** fracción de la cartera que se compra y vende por periodo.
- **Capacidad:** cuánto dinero puede operar una estrategia antes de que su propio impacto en el precio se coma la ganancia.
- **DSR (Deflated Sharpe Ratio):** probabilidad de que el Sharpe observado supere al que esperarías por azar tras probar N configuraciones. **PBO:** probabilidad de que la configuración elegida rinda peor que la mediana de sus rivales fuera de muestra.

### Por qué "absurdamente preciso e infalible" no se puede construir

Cada punto es un mecanismo, no una opinión:

1. **El mercado es casi un juego de suma cero antes de costos y negativo después.** Cada operación tiene alguien del otro lado. Para que tu alfa sea positivo, el de otro tiene que ser negativo, y tu competencia son equipos de cientos de doctores con datos que cuestan $56–80 k por dataset. SPIVA 2025: 79 % de los fondos activos large-cap perdieron contra el S&P 500.
2. **Los costos matan las señales rápidas.** En los 4.000 alphas reales de WorldQuant la ganancia por acción es aproximadamente proporcional a 1/turnover: cuanto más rápido operas, menos ganas por operación, y por debajo de cierto umbral el costo se lo come todo. Medallion opera en milisegundos con costos que un individuo no puede tener.
3. **La escala gigante no es una ventaja que puedas copiar, y Medallion lo demuestra al revés.** Lo que lo hace rentable no escala: por eso dejó de aceptar dinero externo hace años y limita su tamaño. Su ventaja es infraestructura, datos y costos, no "un modelo más preciso".
4. **El alfa publicado decae.** El retorno de los factores cae ~58 % después de publicarse (McLean-Pontiff 2016); entre un tercio y la mitad de los 296 factores publicados probablemente son falsos (Harvey-Liu-Zhu 2016). Lo que lees en un paper rinde la mitad en vivo.
5. **El backtest sobreestima incluso en manos expertas.** Carver (ex Man AHL), con el sistema abierto más riguroso que existe y operando en IBKR desde hace 12 años: Sharpe 1,29 en backtest y 0,80 en vivo. Quantopian, sobre 888 algoritmos: R² de 0,02 entre Sharpe in-sample y OOS.
6. **Tu propio repo ya lo midió.** SMA 10/30 sobre SPY: CAGR 0,4 % contra 11,7 % del buy & hold. El walk-forward cosido de la campaña del 25-10: CAGR 3,4 % contra 15,1 % del buy & hold, y el parámetro "óptimo" saltó de 50/200 en el fold 1 a 10/30 en el fold 2 (inestable, señal típica de ruido). Sobre 20 caminatas aleatorias (precios sin ninguna estructura), los gates laxos aprobaron 11 y los estrictos 4: con suficientes pruebas, el azar pasa los filtros.
7. **Más precisión del modelo no es más dinero.** El mejor modelo de ML en 30.000 acciones y 920 variables explica 0,40 % de la varianza mensual (Gu-Kelly-Xiu 2020). Un ETF diario tiene ~5.000 observaciones en 20 años: cualquier modelo profundo sobre eso memoriza ruido.

### Qué sí es alcanzable

Tendencia a 1/3/12 meses + paridad de riesgo + vol target 10 % sobre ~10 ETF líquidos: **Sharpe neto realista 0,5–0,8, DD de 15–25 %**, y en vivo espera ~0,75× el Sharpe del backtest. Traducido: un retorno parecido al de un índice con, con suerte, la mitad de su caída máxima. Eso es lo que hacen bien los fondos grandes que sí sirven de modelo (Man AHL, AQR, Bridgewater) y lo que este sistema puede hacer bien.

Y la regla que ya está escrita en el playbook y que mantengo: **si nada le gana a un 60/40 con los gates estrictos y el hold-out congelado, la respuesta correcta es indexar**. En ese caso el sistema sigue siendo útil: automatiza el rebalanceo, el control de riesgo y el reporte de una cartera pasiva, que es exactamente lo que hace la mayor parte del dinero institucional.

---

## 2. Estado verificado del sistema (07-11-2026)

| Hecho | Evidencia |
|---|---|
| ~17.900 líneas de Python en 110 módulos, 111 archivos de test, 62 comandos de CLI | `find src -name '*.py' \| xargs wc -l`, `ls tests`, `grep @app.command src/ibtrader/ops/cli.py` |
| CI verde (ruff + mypy + pytest) en `1c9868d` | corrida local en la nube y commit `e7a4d0d` |
| PC = GitHub, árbol limpio | `git log` y `git status` en `C:\dev\apps\IBKR-INVESTMENT-app` |
| En el PC solo hay datos de SPY (caché y vintages) | `data/cache/`, `data/vintages/manifest.json` |
| El freeze de paper congela `sma_crossover` 10/30, universo `["SPY"]`, `long_only` | `data/paper_config_freeze.json` en el PC |
| Paper sin libro ni curva | no existen `data/paper_account.json` ni `data/paper_equity.jsonl` |
| No hay `.env` en el PC (solo `.env.example`): sin token de Tiingo, sin puerta IA configurada | `ls .env*` |
| `IBKRBroker` no se instancia en ningún módulo; `allow_broker_orders=False` | `grep -rn "IBKRBroker(" src` |
| DSR sin mínimo de observaciones | `research/gates.py:271-280`, `research/dsr.py`; `reports/research/research_sim_research_smoke.json` (`n_obs: 24`, `dsr: 0.99997`) |
| ~50 commits en 3 días (24–26 oct), ~15 de ellos "WIP: rescate de trabajo sin commitear", de varios agentes, con reparaciones de archivos truncados | `git log --since 2026-10-24` ("healed truncate", "undo W3 relevo damage") |

---

## 3. Auditoría por módulo

Veredictos: **Mantener** (bien y en uso), **Arreglar** (necesario pero con fallas), **Consolidar** (duplica a otro), **Eliminar** (muerto o dañino).

### 3.1 Datos (`data/`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `providers.py` (Fixture, Yahoo, IBKR, Stooq, Tiingo, `DataQualityGate`) | Tiingo implementado y sin usar (no hay token). Yahoo: sin SLA, solo supervivientes, ajustes retroactivos. Stooq documentado como no funcional. | **Arreglar:** Tiingo como fuente primaria, Yahoo como segunda fuente de contraste, quitar Stooq. |
| `vintage.py` (parquet por `vintage_date` + manifiesto SHA-256) | Bien diseñado, es lo que hacen Man (ArcticDB) y Jane Street. | **Mantener.** |
| `universe.py` + `config/universe-10etf.json` (ciclo de vida, `listed_from`/`delisted_on`) | Bien. Varias fechas de alta "puestas de memoria" según el propio archivo. | **Arreglar:** validar contra `TiingoProvider.fetch_metadata`. |
| `validators.py`, `lineage.py`, `cache.py`, `service.py` | Validación básica correcta. | **Mantener.** |
| `downloader.py` | Ruta vieja de yfinance paralela a `service.py`. | **Consolidar** en `service.py`. |

**Falta:** reconciliación entre fuentes (si Tiingo y Yahoo difieren más de X pb en un cierre, alerta y no se opera ese día); timestamp de recepción en cada barra (Jane Street: "con la hora en que lo recibimos"); chequeo de frescura antes de generar órdenes (si el último cierre no es el de hoy, no se opera).

### 3.2 Señales (`strategy/`, `pipeline/`, `intelligence/`, `ensemble/`, `engine/`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `pipeline/` (rules → forecast → combine → vol → sizing → portfolio_stage → buffering; `system.py`) | El corazón de la fase 2, modelado en pysystemtrade, con tests. Nunca corrido sobre datos reales del universo. | **Mantener y usar.** Es el único motor de señales que debería quedar. |
| `strategy/pipeline_strategy.py`, `strategy/tsmom.py` | Puentes al motor de backtest. | **Mantener.** |
| `strategy/sma_crossover.py`, `mean_reversion.py`, `rotation.py` | Familias ya rechazadas sobre SPY o sin uso en producción. | **Archivar** como baselines de test; fuera de la ruta de paper. |
| `engine/decision.py` + `engine/paper_policy.py` + `ensemble/combiner.py` + `intelligence/features.py` + `intelligence/regime.py` | Segundo motor de decisiones (fase 1, un solo activo, SMA + régimen VIX) paralelo al pipeline. Dos motores = dos verdades. | **Consolidar:** que `paper-run` use el pipeline; luego eliminar este camino. |
| `regime/gmm.py` | GMM de régimen. La evidencia del playbook lo deja como filtro de volatilidad, no como alfa. | **Mantener como opcional**, apagado por defecto. |
| `intelligence/market_radar.py`, `brief.py`, `prompt_pack.py` | Triage y explicación, no señal. Bien acotado. | **Mantener** (ver sección 6). |

### 3.3 Cartera y sizing (`portfolio/`, `pipeline/sizing.py`, `risk/sizing.py`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `portfolio/boxes.py`, `hrp.py`, `multiplier.py` | Paridad de riesgo por cajas, HRP y multiplicadores de diversificación: lo correcto según la evidencia (Markowitz sin regularizar necesita ~3.000 meses de datos). | **Mantener.** |
| `portfolio/sizing.py`, `pipeline/sizing.py`, `risk/sizing.py` | Tres lugares para el sizing. | **Consolidar** en `pipeline/sizing.py`. |

**Falta:** tamaño mínimo de orden en dólares. Con el mínimo de $1 por orden de IBKR, una orden de $1.000 cuesta 10 pb solo de comisión; el playbook pide órdenes ≥ $5.000. El sistema debe redondear o saltarse órdenes por debajo de ese umbral, y eso depende del capital que aún no has definido.

### 3.4 Riesgo (`risk/`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `risk/manager.py`, `state_machine.py`, `loss_metrics.py`; kill switch; `halt_next_day` fail-closed | Sólido y probado (FSM, matriz de estados, persistencia del drawdown). | **Mantener.** |

**Fallas:**
- El gestor de riesgo vive dentro del backtest y de los runners; **no hay una capa de riesgo pre-trade** entre "pesos objetivo" y "orden al broker", porque no hay ruta al broker.
- Los límites por defecto del freeze (`max_position_pct=100`, `max_total_exposure_pct=100`) tienen sentido para un solo ETF, no para 10.
- La regla de DD del playbook (−20 % desde el máximo → vol target al 5 %; −30 % → parar y revisar) no está implementada como regla de producción. Ojo: el playbook también documenta que **salir por stop de drawdown destruye valor en tendencia** (Graham Capital: IR 0,52 → 0,09 con stop a −10 %). Por eso la regla es recortar vol, no liquidar.

**Falta (pre-trade, lo que todo fondo tiene y es barato):** tope de nocional por orden; tope de órdenes por corrida; "fat finger" (rechazar un precio límite a más de ±3 % del último cierre); whitelist; comprobación de que la cuenta conectada es la esperada; y un **dead man's switch**: si el job diario no corrió, no hubo latido o los datos no están frescos, no se generan órdenes.

### 3.5 Ejecución (`broker/`, `execution/`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `broker/ibkr.py` | Nunca se instancia. Envía MKT/LMT y devuelve el `orderId` tras `sleep(0.1)`, sin seguir el estado de la orden. | **Arreglar** (ver abajo). |
| `broker/simulated.py`, `execution/session.py` (calendario NYSE), `execution/costs.py` (modelo de costos IBKR + sanidad ≥ 2,5 pb) | Buen simulador y buen modelo de costos. | **Mantener.** |
| `execution/passive_aggressive.py` | 28 líneas; la idea (límite pasivo que se vuelve agresivo) es correcta, falta la implementación. | **Arreglar.** |
| `execution/order.py`, `execution/portfolio.py` | Sin ninguna referencia en `src` ni `tests`. | **Eliminar.** |

**Fallas concretas de `broker/ibkr.py`:**
1. No hay máquina de estados de la orden (enviada → aceptada → parcial → llena / cancelada / rechazada). El `orderId` se devuelve antes de saber si IBKR la aceptó.
2. No hay idempotencia: si el proceso se cae tras enviar y se reinicia, puede volver a mandar la misma orden. Falta un `orderRef` determinista por (fecha, símbolo, lado) y consultar órdenes abiertas antes de enviar.
3. No escucha `errorEvent` ni `orderStatusEvent`; un rechazo pasa desapercibido. El playbook ya documenta el caso de "Read-Only API" activado: las órdenes no llegan **y no hay error**.
4. `get_quote` hace `reqMktData` y nunca lo cancela (fuga de suscripciones) y no distingue datos retrasados de datos en vivo.
5. `get_positions` convierte a `int`; no lee caja ni NetLiquidation para reconciliar.
6. No respeta el límite de la API (50 mensajes/s; la tercera violación cierra la sesión).
7. Usa `MarketOrder` por defecto. Para ETFs líquidos en una cartera de rebalanceo diario o mensual, lo correcto es límite al punto medio con tiempo de espera y luego `Adaptive`, solo en horario regular.

### 3.6 Monitoreo y operación (`ops/`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `autopilot`, `paper_curve`, `paper_status`, `paper_vs_oos`, `stack`, `shadow`, `slippage_ledger`, `config_freeze`, `alerts`, `urgency_age`, `ibc_checklist`, `open_orders`, `simple_ui`, scripts de Task Scheduler | Mucho trabajo de operación, bien probado, pero midiendo un paper sin órdenes reales. | **Mantener**; reconectar al broker real cuando exista. |
| `ops/journal.py`, `killswitch.py`, `status.py` | En uso desde la CLI. | **Mantener.** |
| `ops/cli.py` (1.690 líneas, 62 comandos) | Un solo archivo con toda la superficie. Es donde más se han truncado archivos entre agentes. | **Arreglar:** partir en `cli/research.py`, `cli/paper.py`, `cli/ops.py`, `cli/data.py`. |

**Falta:** un canal de alertas que llegue al teléfono (correo o Telegram), un latido diario ("el job corrió, N órdenes, todo reconciliado") y la reconciliación posiciones/caja contra el broker.

### 3.7 Research y validación (`research/`, `validation/`, `backtest/`, `diagnostics/`)

| Módulo | Estado | Veredicto |
|---|---|---|
| `backtest/engine.py` (next-open, costos, `restricted` por barra), `metrics.py` | Sólido. | **Mantener.** |
| `validation/walkforward.py`, `research/{cpcv,pbo,dsr,gates,registry,suite,cost_stress,embargo_sensitivity,turnover_diag,benchmarks,report}` | Más validación que cualquier framework abierto. | **Mantener**, con los arreglos de abajo. |
| `research/portfolio_runner.py` (`research-portfolio`) | El runner correcto para la fase 2 (benchmarks 60/40, carteras aleatorias, DSR, PBO, ledger de pruebas). Nunca corrido con datos reales. | **Mantener y correr.** |
| `research/{dsr_sma,pbo_sma,cpcv_sma}`, `tsmom_runner`, `mean_reversion_runner`, `xsection_runner`, `multi_asset`, `loss_mitigation` | Runners por familia sobre un solo activo, anteriores al runner de cartera. | **Archivar** cuando `research-portfolio` sea el camino único. |
| `research/market_analyzer.py` (WARDEN-X9, "12 motores + meta-ensemble"), `warden_engines.py`, `panel.py` | Triage que invita a mirar muchos indicadores hasta encontrar una historia: es exactamente el "grado de libertad del investigador" que infla el número real de pruebas sin que el registro lo cuente. | **Eliminar** (o congelar fuera de la CLI). |
| `backtest/splits.py`, `ml/model.py` | Sin referencias. `ml/cv.py` sí se usa. | **Eliminar** los dos primeros. |
| `diagnostics/suspicious.py` (BacktestSkeptic) | Útil. | **Mantener.** |

**Fallas que cambian veredictos:**
1. **DSR sin mínimo de observaciones.** Con `n_obs = 24` el error estándar del Sharpe se calcula igual y el gate dio 0,99997. Arreglo: el gate de DSR debe exigir `n_obs ≥ 252` (un año diario) y, si no, marcar `dsr_ok = False` con motivo `insufficient_obs`. Lo mismo para PBO y CPCV con su mínimo (el playbook: S = 16 sobre ≥ 4 años diarios).
2. **N se cuenta por corrida, no por proyecto.** El DSR deflacta por las pruebas de *esta* corrida. Las de corridas anteriores sobre los mismos datos también cuentan (cada vez que miraste y cambiaste algo). Arreglo: un ledger global de pruebas por dataset (`reports/research/trials_ledger.jsonl` ya existe en el runner de cartera: hacerlo obligatorio para todo y sumar N entre corridas).
3. **t ≥ 3 no está como gate explícito** (t = Sharpe × √años, Harvey-Liu-Zhu). Añadirlo.

### 3.8 ML (`ml/`)

`ml/cv.py` (CV purgada) se queda. `ml/model.py` (gradient boosting) está muerto y, con ~5.000 observaciones por ETF, debe seguir muerto. Si algún día se usa ML, que sea para escalar el tamaño de una señal ya validada (meta-labeling), nunca para generarla.

---

## 4. Qué quitar, en una lista

| Quitar | Por qué |
|---|---|
| `backtest/splits.py`, `execution/order.py`, `execution/portfolio.py`, `ml/model.py` | Sin referencias en `src` ni `tests`. |
| Motor de fase 1 (`engine/decision.py`, `engine/paper_policy.py`, `ensemble/combiner.py`, `intelligence/features.py`, `intelligence/regime.py`) | Duplica al pipeline con otra lógica. Antes, mover `paper-run` al pipeline y `compute_breadth` a `market_radar`. |
| `research/market_analyzer.py`, `warden_engines.py`, `panel.py` y su CLI | Fomentan buscar historias entre 12 indicadores; inflan N sin registrarlo. |
| `StooqProvider` | Documentado como no funcional. |
| Direcciones `long_short` y `short_only` en la ruta de producción | Fuera del mandato (ETFs largos, sin apalancamiento sin límite) y sin evidencia en este universo. Se pueden quedar en research. |
| Runners por familia de un solo activo (`*_sma`, `tsmom_runner`, `mean_reversion_runner`, `xsection_runner`, `multi_asset`) | Sustituidos por `research-portfolio`. Archivar tras la primera corrida real. |
| Commits "WIP: rescate" de varios agentes en paralelo | Producen truncados y reparaciones. Un agente a la vez sobre `main`. |

Efecto estimado: ~3.000–4.000 líneas menos y un solo camino datos → señal → cartera → riesgo → orden.

---

## 5. Diseño de infraestructura: lo que escala hacia abajo

### Qué se copia de los fondos grandes y qué no

| Se copia (barato, con evidencia) | No se copia (no escala a una persona) |
|---|---|
| Riesgo como parámetro ex ante y proceso separado de la estrategia (Millennium) | HFT, colocation, latencia de milisegundos (Medallion) |
| Datos point-in-time versionados con hash (Man/ArcticDB, Jane Street) | Datos alternativos de $56–80 k por dataset |
| Validación con presupuesto de pruebas, hold-out congelado, DSR/PBO (AHL, LdP) | Fábrica de millones de alphas (WorldQuant) |
| Mismo código para simulación y producción (Cubist, Jane Street) | Kafka, Kubernetes, microservicios, equipos de SRE |
| Costos medidos con fills propios (AQR) | Apalancamiento 10–20× de los pods |
| Reconciliación diaria y post-mortems (pysystemtrade, QuantConnect) | Deep learning sobre precios diarios |
| Pocas señales económicas, diversificadas (tendencia + paridad de riesgo) | Cientos de gestores compitiendo por capital |

Infraestructura: **un PC con Windows, Task Scheduler, SQLite, Parquet, IB Gateway con IBC.** Es suficiente para una cartera de 10 ETF con rebalanceo diario o semanal; añadir servidores o colas solo añade formas de fallar.

### Flujo diario de producción (una corrida por día, después del cierre)

```
16:30  1. DATOS       Tiingo (primaria) + Yahoo (contraste) → vintage del día con SHA-256
                      ├─ frescura: último cierre == hoy hábil NYSE, si no → NO_TRADE
                      └─ reconciliación entre fuentes: |Δcierre| > 20 pb → NO_TRADE + alerta
16:35  2. SEÑALES     pipeline.run_system (config congelada, hash verificado)
                      → pesos objetivo por ETF
16:36  3. RIESGO      FSM (DD, pérdida diaria/acumulada, kill switch) + pre-trade:
                      tope por orden, fat-finger ±3 %, whitelist, tamaño mínimo $,
                      cuenta esperada, órdenes máximas por corrida
                      → lista de órdenes aprobadas (o NO_TRADE con motivo)
09:31  4. EJECUCIÓN   (siguiente apertura, mismo supuesto que el backtest)
       (día t+1)      OrderManager: orderRef idempotente, límite al medio,
                      timeout → Adaptive, solo horario regular, máquina de estados
16:00  5. FILLS       ledger de slippage (precio de decisión vs fill, en pb)
16:20  6. RECONCILIA  posiciones y caja internas vs IBKR; diferencia → kill + alerta
16:25  7. REPORTE     curva vs backtest OOS, tracking error, costos del día,
                      latido "OK" o alerta, al teléfono
```

Tres reglas de diseño que no se negocian:
1. **El riesgo es un proceso aparte y tiene la última palabra.** La estrategia propone pesos; el módulo de riesgo los recorta o los veta; el broker solo acepta órdenes firmadas por el módulo de riesgo. Ningún componente (incluido Claude) puede saltarlo.
2. **Fail-closed en todo.** Si falla cualquier paso, la acción por defecto es no operar y avisar. Nunca "operar con los datos de ayer".
3. **Paridad research → producción.** El mismo `run_system` y el mismo modelo de costos en backtest, paper y live. El paper debe enviar órdenes reales a la cuenta paper de IBKR; si no, no mide ejecución.

### Componentes nuevos

| Componente | Qué hace | Dónde |
|---|---|---|
| `execution/order_manager.py` | Máquina de estados de orden, `orderRef` idempotente, consulta de órdenes abiertas antes de enviar, escucha de `errorEvent`/`orderStatusEvent`, límite de mensajes/s | nuevo, sobre `broker/ibkr.py` |
| `risk/pretrade.py` | Chequeos pre-trade de la sección 3.4 | nuevo |
| `ops/reconcile.py` | Posiciones + caja vs broker; diferencias → kill switch | extiende `ops/stack.py` |
| `ops/heartbeat.py` + notificador | Latido diario y alertas por correo/Telegram | extiende `ops/alerts.py` |
| `data/crosscheck.py` | Reconciliación Tiingo vs Yahoo y frescura | nuevo |
| `ops/run_daily.py` | Orquesta los 7 pasos con un solo punto de entrada para Task Scheduler | sustituye a varias tareas sueltas |
| Golden files en CI | `expected_statistics.json` por estrategia sobre fixtures | `tests/golden/` |

---

## 6. Claude por API: para qué sí y para qué no

### Lo que ya existe y está bien

`intelligence/brief.py` + `prompt_pack.py`: Claude solo pasa por la puerta (`ANTHROPIC_BASE_URL=https://ia.zynoratek.com`, token de proyecto `pia_…`), el repo nunca guarda la clave real, siempre hay texto determinista de respaldo, se revisa `stop_reason`, no se manda `temperature` (la API `2026-10-21` lo rechaza con 400), el system prompt se cachea, y el prompt prohíbe inventar precios o recomendar órdenes. Ese es el patrón correcto. Una mejora menor: `output_config` se puede pasar como argumento directo de `messages.create` en lugar de `extra_body`.

### Para qué NO usar Claude

1. **No genera señales de compra/venta ni decide tamaños.** Mecanismo principal: **contaminación temporal**. Un modelo entrenado con texto hasta 2026 "sabe" lo que pasó en 2020–2025, así que cualquier backtest de señales generadas por un LLM sobre ese periodo tiene look-ahead incorporado y no hay forma de quitarlo. No se puede validar con las herramientas del repo, y lo que no se puede validar no entra.
2. **No es determinista.** La misma entrada puede dar otra salida; un sistema de órdenes tiene que poder reproducirse bit a bit desde el vintage y el hash de config.
3. **La evidencia publicada es mala para tu caso.** GPT-4 sobre titulares: Sharpe 2,97 bruto que muere con 20 pb de costo y decayó de 6,5 a 1,2 en 30 meses (Lopez-Lira & Tang 2025), y es alfa de acciones individuales alrededor de noticias, irrelevante para ETFs de índice.
4. **Nunca está en la ruta de órdenes.** Si Claude se cae, tarda o se niega, el sistema opera igual. Todas las llamadas son asíncronas y con respaldo determinista.

### Para qué SÍ (ordenado por valor)

| # | Uso | Modelo / modo | Por qué aporta |
|---|---|---|---|
| 1 | **Revisión de código antes de cada push** a `main`: buscar look-ahead, fugas de datos, bypass del riesgo, cambios de defaults de riesgo, archivos truncados | `claude-opus-5-5`, effort `high` (o Claude Code con `/code-review`, que ya usas) | El riesgo número uno de este repo hoy no es de mercado: es un bug introducido por un agente. Lo más barato y con mayor retorno. |
| 2 | **Auditor de research ("abogado del diablo")**: recibe la hipótesis escrita, el ledger de pruebas y el reporte honesto, y responde con salida estructurada: ¿la hipótesis se escribió antes?, ¿N real vs N registrado?, ¿el hold-out se abrió más de una vez?, ¿qué haría falta para creerlo? | `claude-opus-5-5`, effort `high`, structured outputs | Ataca el sesgo de quien investiga, que es lo que los gates no pueden ver. |
| 3 | **Triage de alertas e incidentes**: cuando falla la reconciliación, el job o un dato, recibe logs + estado y devuelve `{severidad, causa_probable, paso_del_runbook, ¿requiere_humano?}` | `claude-sonnet-5-5`, effort `medium`, structured outputs | Reduce el tiempo de diagnóstico a las 7 a.m. No actúa: propone. |
| 4 | **Informe diario y explicación de decisiones** (lo que ya hace `ai_brief`): por qué cada peso cambió, desde el JSON de hechos | `claude-haiku-5-5`, effort `low` | Supervisión en 30 segundos. Costo despreciable. |
| 5 | **Vigilancia de eventos del universo** (no de noticias de mercado): cierres o fusiones de ETF, cambios de índice subyacente, avisos de IBKR, calendario FOMC. Salida: "revisar universo / revisar datos", nunca "comprar/vender" | `claude-sonnet-5-5` vía **Batch API** (50 % más barato, nocturno) | Evita que un cambio estructural rompa el sistema en silencio. |
| 6 | **Asistente de la checklist fiscal México/SAT**: resumir y comparar documentos que tú le des (W-8BEN, estados de cuenta, constancias) | `claude-opus-5-5` | Ahorra tiempo, pero no sustituye a un contador. |

### Reglas de integración

- **Solo por la puerta**, como hoy (`puerta_config_error`). Una variable de proceso (`x-proceso`) por uso para medir el gasto por caso.
- **Salidas estructuradas siempre** (`output_config.format` con JSON Schema, `additionalProperties: false`), validadas con Pydantic antes de usarlas; si la validación falla, se descarta y queda el texto determinista.
- **Todo al journal:** modelo, hash del prompt, hash de los hechos, `stop_reason`, tokens y respuesta. Una explicación que no se puede auditar después no sirve.
- **`effort` explícito** en cada llamada (en Opus 5.5 y Haiku 5.5 el default es `medium`); sin `temperature`, `top_p` ni `top_k`; sin prefill.
- **Caché del system prompt** (estable y primero) y nada variable antes del último `cache_control`.
- **Presupuesto mensual con corte**: si se pasa, todo vuelve a determinista.
- **Claude nunca escribe en `data/`, en la config congelada ni en el kill switch.** Solo lectura sobre hechos ya calculados.

### Esqueleto del triage (uso 3)

```python
import json
import anthropic
from pydantic import BaseModel, ValidationError

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["info", "warn", "critical"]},
        "likely_cause": {"type": "string"},
        "runbook_step": {"type": "string"},
        "needs_human": {"type": "boolean"},
    },
    "required": ["severity", "likely_cause", "runbook_step", "needs_human"],
    "additionalProperties": False,
}

class Triage(BaseModel):
    severity: str
    likely_cause: str
    runbook_step: str
    needs_human: bool

def triage_incident(facts: dict, system_prompt: str) -> Triage | None:
    """Propone, no actúa. None = quedarse con la alerta determinista."""
    if puerta_config_error() is not None:        # ya existe en intelligence/brief.py
        return None
    client = anthropic.Anthropic()               # ANTHROPIC_BASE_URL (puerta) + token pia_
    try:
        r = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=2000,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(facts, sort_keys=True)}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}},
            extra_headers={"x-proceso": "ibtrader-triage"},
        )
    except anthropic.APIError:
        return None
    if r.stop_reason in ("refusal", "max_tokens"):
        return None
    text = next((b.text for b in r.content if b.type == "text"), "")
    try:
        return Triage.model_validate_json(text)
    except ValidationError:
        return None
```

### Costo esperado (precios de lista, 07-11-2026)

| Uso | Volumen | Costo aproximado |
|---|---|---|
| Informe diario, Haiku 5.5 ($0,10 / $0,50 por millón de tokens de entrada / salida) | ~3 k entrada + 400 salida, 21 días | < $0,05 al mes |
| Triage, Sonnet 5.5 ($2 / $10) | ~10 k + 1 k, 10 incidentes | ~$0,30 al mes |
| Revisión de código, Opus 5.5 ($4 / $20) | ~30 k + 3 k, 20 pushes | ~$3,60 al mes |
| Auditor de research, Opus 5.5 | ~50 k + 4 k, 4 corridas | ~$1,10 al mes |

Del orden de **$5 al mes**. El costo no es la restricción; la disciplina de dejarlo fuera de la ruta de órdenes sí lo es.

---

## 7. Plan priorizado

Cada fase tiene una definición de hecho verificable. No se pasa a la siguiente sin cumplirla.

### P0 — Esta semana: decisiones tuyas y arreglos que cambian veredictos

| Paso | Quién | Hecho cuando |
|---|---|---|
| Fijar los cuatro datos que siguen sin respuesta: **capital inicial, DD máximo tolerado, horizonte en años, si la cuenta IBKR existe** | Adam | Escritos en `.env` / config y en la memoria del proyecto |
| Token de Tiingo Power ($30/mes) en `.env` como `DATA__TIINGO_TOKEN` | Adam | `ibtrader download-data` baja los 11 símbolos del universo |
| DSR/PBO/CPCV con mínimo de observaciones; gate `t ≥ 3`; N acumulado entre corridas | código | Test que reproduce el caso `n_obs=24` y ahora falla el gate |
| **Descongelar el paper de SMA 10/30 sobre SPY** (`config-freeze --force` solo después de P1) | Adam + código | Freeze nuevo sobre la config que salga de P1, o sobre 60/40 si nada pasa |

### P1 — Semanas 1–2: la primera evidencia real

- `ibtrader research-portfolio` sobre el universo de 10 ETF con `RESEARCH__HOLDOUT_START` = hoy − 2 años, presupuesto de pruebas declarado antes y la hipótesis escrita en `docs/research/hipotesis/`.
- Una sola apertura del hold-out, al final.
- **Hecho cuando:** hay un reporte con veredicto honesto contra 60/40, RPAR y 1.000 carteras aleatorias. Si es FAIL, la recomendación escrita es indexar (y el sistema se usa para rebalancear la cartera pasiva).

### P2 — Semanas 3–5: ejecución real en la cuenta paper

- `order_manager.py`, `risk/pretrade.py`, `ops/reconcile.py`, `ops/run_daily.py`.
- Primero en **modo sombra** (genera órdenes, las registra, no las envía) una semana; después órdenes reales a la cuenta paper de IBKR.
- **Hecho cuando:** 10 días hábiles seguidos con órdenes paper reales, reconciliación sin diferencias, ledger de slippage con fills reales y latido diario recibido.

### P3 — En paralelo a P2: observabilidad y Claude

- Notificador (correo o Telegram), latido diario, reporte de tracking error.
- Claude: revisión de código pre-push (uso 1) y triage (uso 3); el informe diario ya existe.
- **Hecho cuando:** una falla provocada a propósito (borrar el vintage del día) produce `NO_TRADE`, alerta al teléfono y un triage estructurado en el journal.

### P4 — Limpieza (después de P2, para no romper lo que funciona)

- Eliminar lo de la sección 4, partir `cli.py`, golden files en CI.
- **Hecho cuando:** CI verde, golden files iguales antes y después, ~3.000 líneas menos.

### P5 — Paper disciplinado (3 meses de calendario)

- Config congelada, sin retoques motivados por el último mes. Matar si el drawdown es incompatible con el Sharpe asumido. Esperar ~0,75× el Sharpe del backtest.

### P6 — Capital real pequeño (solo si P5 pasa)

- Tamaño que mantenga órdenes ≥ $5.000; −20 % desde el máximo → vol target 5 %; −30 % → parar y revisar; checklist fiscal México/SAT (W-8BEN vigente, retención del 10 % en dividendos por tratado, acreditamiento contra ISR) revisada con un contador.

### Reglas de proceso (para que el repo deje de romperse)

- Un agente a la vez sobre `main`; nada de commits "WIP: rescate" de varios agentes en paralelo.
- Todo cambio de defaults de riesgo o de gates necesita un test que lo fije.
- Ningún parámetro se cambia por el resultado del último mes.

---

## Fuentes

Las cifras externas vienen del playbook del 21-10 y sus siete anexos (`docs/research/quant-funds-2026-10-21/`), donde cada una tiene enlace, fecha y marca primaria/secundaria. Las cifras internas vienen de los archivos citados en la sección 2 (repo en `1c9868d` y estado del PC al 07-11-2026). Los modelos y precios de Claude, de la referencia de la API de Anthropic vigente a esta fecha.
