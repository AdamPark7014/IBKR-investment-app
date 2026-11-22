# RELEVO

## Hecho (2026-11-21 22:30 Puebla, claude-code — revisión de todo el sistema y vigía; nada del PC se tocó)
- Diagnóstico: `docs/research/BRECHAS-SISTEMA-2026-11-22.md`. La señal está en su techo (~0,6); la brecha es la operación.
- **Vigía** (`ibtrader vigia`, `ops/vigia.py`, `scripts/schedule-vigia.ps1`): cada 15 min corre el plan o la ejecución
  que falte. Sin campos nuevos de configuración: el freeze no cambia. Estado en `data/vigia_state.json`, candado
  `data/vigia.lock`. Avisos una vez por sesión: `gateway_cerrado`, `sesion_perdida`, `ejecucion_agotada`.
- **Sin instalar en el PC**: falta el sí de Adam (tarjeta de decisión). Instalar = `git pull` + `schedule-vigia.ps1
  -Action Register` (desactiva plan y ejecución de hora fija; `Unregister` las reactiva).
- Pendientes por impacto: Telegram, IBC, equipo siempre encendido, respaldo de `data/`, paper contra backtest mensual,
  tope por clase de activo (requiere re-congelar), simulacros de fallo, carry.

## Hecho (2026-11-21 noche, claude-code — fase 3: momentum relativo; nada de paper se tocó)
- Informe: `docs/research/FASE-3-MOMENTUM-RELATIVO-2026-11-21.md`. Regla nueva `relmom_1_3_12` (momentum menos la media
  de los pares de su clase; `SystemConfig.peer_groups`), apagada por defecto.
- IC 0,07 (21 d) y 0,10 (63 d), positivo en las dos mitades; correlación 0,50 con la tendencia. Prueba pareada contra
  paper (2004-2026): Sharpe 0,66 contra 0,60, +0,05 (−0,07 a +0,18) → «indistinguible». Caída máxima −15,1 % contra
  −10,9 %, coste 0,78 % contra 0,49 %. **No entra a paper. No reajustar la señal.**
- Conclusión de las fases 1 a 3: con 10 ETF solo en largo el techo es Sharpe ~0,6. Queda carry (necesita dividendos
  por ETF de Tiingo, se bajan desde el PC). La prioridad real es la fase 0.

## Hecho (2026-11-21 noche, claude-code — fases 1 y 2 del plan maestro; nada de paper se tocó)
- Informe: `docs/research/FASES-1-2-RESULTADOS-2026-11-21.md`. Datos: Tiingo desde 2002 (32 ETF) en el PC,
  `reports/research_data/` (bajados con `scripts/descargar_historia.py`). Ventana 2004-01-28 → 2026-11-20.
- **Fase 1 (2008 dentro):** núcleo 25 % + tendencia 75 % Sharpe 0,60 contra 0,48 de la tendencia sola; diferencia
  +0,12 (−0,06 a +0,32) → «indistinguible» (antes «promover» con ventana desde 12-2008). En 2008 la tendencia sola
  +9,2 %, la mezcla −1,4 %, el 60/40 −32,3 %. Recomendación: dejar el paper como está, bajar la expectativa a ~0,6.
- **Fase 2 (26 ETF):** no mejora. Sharpe 0,52 contra 0,60 (−0,09; −0,23 a +0,07). Correlación 0,94 con el universo
  de 10; el reparto por cajas lleva riesgo a bonos y divisas sin prima. El universo se queda en 10 ETF.
- Código: `stress_report`, `run_universe_study`, `settings_with_universe_spreads` en `research/challenger.py`.
- Siguiente: fase 3, momentum relativo dentro de cada clase sobre los 10 ETF, definido por escrito antes de correr.

## Hecho (2026-11-21 16:25 Puebla, claude-code — fase 0 aplicada en el PC)
- PC en main `803b80b`. `.env`: + `PRETRADE__MAX_CASH_ORDER_NOTIONAL_USD=100000` (copia `data/logs/env.antes-fase0-20261121.bak`).
  Freeze re-congelado: `534b520bbe2103ad`.
- Plan corrido a mano con `run-task.ps1`: 89 s, `status ok`, latido escrito. 9 órdenes pendientes para el lunes 23-11
  (run_date 2026-11-20): BIL BUY 1 091 (≈99 925 USD), SPY 14, IEF 109, TIP 94, VNQ 108, PDBC 77, TLT 20; ventas VEA 24 y VWO 46.
  Reemplazó el pending de la mañana (estrategia vieja). Copiloto: `sin_opinion` (la puerta devolvió vacío; sin investigar).
- **Por qué no corre solo (medido, sin cambiar nada):** tareas con LogonType Interactive (solo con sesión iniciada);
  equipo con Modern Standby S0 y temporizadores de reactivación apagados en batería (WakeToRun no despierta); nada
  arranca el Gateway (sin IBC, sin acceso en Inicio) y no había proceso ni puerto 4002.
- `ibtrader-autopilot` y `ibtrader-paper-reconcile` siguen activas y fallando a diario (0x1). `heartbeat-check` dio 0x2.
  `ibtrader-ibc-check` no existe. El `*>>` de `run-task.ps1` mete `NativeCommandError` en el log (ruido).
- Pendiente de Adam: laptop enchufada y sin suspender en horario de bolsa, abrir Gateway paper (2FA semanal), decidir
  Telegram (bot) e IBC (guardaría credenciales de IBKR en un archivo local).

## Hecho (2026-11-21 tarde, claude-code — fase 0 del plan maestro: que corra solo; Adam eligió «en mi laptop actual»)
- **Por qué murió el plan del sábado 10:26**: llegó hasta escribir el punto de equity del 20-11 y se colgó en el copiloto
  (el SDK de Anthropic espera 10 min y reintenta) antes del latido y del informe. Ahora latido e informe se escriben
  antes del copiloto, y la llamada a la puerta tiene `AI_TIMEOUT_SEC=45` y un reintento. Yahoo (contraste) con `timeout=15`.
- **Tope por orden para letras**: `PRETRADE__MAX_CASH_ORDER_NOTIONAL_USD` (None = igual que el general). Solo aplica a los
  ETF de la caja `cash`; pretrade y `build_rebalance_orders` usan el mismo tope (`risk.pretrade.order_cap`). Entra en el
  freeze: hay que re-congelar al actualizar.
- Telegram sigue sin configurar (`OPS__TELEGRAM_BOT_TOKEN`/`CHAT_ID` vacíos): las alertas solo van a `data/alerts.jsonl`.

- **2026-11-21 (claude-code) — Plan maestro** (Adam: «más predictivo, como los fondos grandes»): `docs/research/PLAN-MAESTRO-2026-11-21.md`.
  Tesis: IC de la tendencia lenta 0,04–0,10 (normal en la industria); falta amplitud, no complejidad. Fases: 0 operación
  confiable → 1 medición (2008, costes reales) → 2 universo de 25–35 ETF → 3 carry, momentum relativo, valor → 4 fallos →
  5 ML solo para combinar → 6 real. Nuevo `research/predictive.py` (IC por regla y horizonte; diagnóstico, no cuenta como prueba).

## Hecho (2026-11-21 tarde, claude-code — núcleo 60/40 + tendencia activado en paper, con el sí de Adam)
- Adam eligió en la tarjeta «Sí, 25 % núcleo + 75 % tendencia». PC en main `1de7dc1`.
- `.env`: `STRATEGY__PARAMS={"core_weights":{"SPY":0.6,"IEF":0.4},"core_frac":0.25}` (única línea cambiada). Copias:
  `data/logs/env.antes-nucleo-20261121.bak` y `data/logs/paper_config_freeze.antes-nucleo-20261121.json`.
- Freeze re-congelado: hash `be1e46753ec10540` (antes `31285ba17f3bcf14`). **El conteo de paper empieza de nuevo el
  2026-11-21**; `paper_equity.jsonl` no se tocó (los 5 puntos anteriores son de la estrategia vieja).
- Pesos objetivo con datos al 2026-11-20: BIL 60,4 %, SPY 15,8 %, IEF 12,2 %, VNQ 3,2 %, TIP 3,1 %, PDBC 2,1 %,
  TLT 1,2 %, VEA 0,8 %, GLD 0,7 %, VWO 0,7 %. Suman 1.
- `chequeo`: `listo_sombra=true`, `listo_paper=false` por dos pendientes: Gateway cerrado (127.0.0.1:4002) y latido
  vencido (116 h). Sin órdenes, sin plan nuevo. No había proceso de plan colgado.
- Sigue pendiente: que el sistema corra a diario (laptop y Gateway) y el tope de 10k por orden para BIL.

## Hecho (2026-11-21, claude-code — «mejora e hiper perfecciona el algoritmo»)
- **Nada de producción cambió**: ni `.env`, ni freeze, ni tareas. Informe: `docs/research/MEJORA-ALGORITMO-2026-11-21.md`.
- Nuevo `ibtrader research-retador` (`research/challenger.py`): prueba pareada retador contra titular, Sharpe sobre
  BIL, bootstrap por bloques de 21 sesiones, Bonferroni. Datos: vintage `2026-11-08` (Tiingo 2006→2026), ventana
  2008-12-09 → 2026-11-06, corrido en la nube con los parquet del PC.
- Titular (lo que corre en paper, `STRATEGY__PARAMS={}`): CAGR 4,7 %, Sharpe 0,55 contra BIL, caída −11,0 %.
  Variantes de señal y perfiles de riesgo (`SystemConfig.box_budgets`): todas indistinguibles del titular.
- **Única que pasa**: núcleo pasivo 60/40 al 25 % + tendencia al 75 % (`core_weights`, `core_frac`): CAGR 6,0 %,
  Sharpe 0,76, caída −9,5 %, diferencia de Sharpe +0,21 (IC al 99,3 %: +0,01 a +0,41). Al 50 % rinde más (7,3 %)
  pero no pasa y SPY puede chocar con `max_weight_per_symbol` 0,4. La ventana no incluye 2008.
- Para activarla en paper (solo con el sí de Adam): `STRATEGY__PARAMS={"core_weights":{"SPY":0.6,"IEF":0.4},"core_frac":0.25}`
  y re-congelar.
- **Paper casi no corre**: 2 ejecuciones en 9 sesiones (10-11 y 11-11). Sin plan el 12, 13 y 17–20 (laptop apagada a
  las 18:00); el 17-11 el Gateway no respondió (`broker_unreachable`) y el plan del 16 caducó. El plan de hoy
  (sábado 10:26) quedó sin línea final tras el cross-check de Yahoo (`VEA: possibly delisted`); sin investigar.
  87 % del millón sigue en efectivo: objetivo 65 % BIL con tope de 10k por orden = más de 60 sesiones.
- Registro: 102 pruebas en `portfolio_trials.jsonl`. No añadir variantes de señal; lo pendiente es historia desde 2002
  para medir la mezcla con 2008 dentro.

- **2026-11-14 (claude-code) — Limpieza de documentación (Adam: «quita documentación y unifica»).** Borrados 13 documentos obsoletos sin referencias (auditorías, planes y prompts viejos; están en el historial de git). Índice único del repo: `docs/INDICE.md`; índice de todos los proyectos: `C:\dev\DOCS.md`; memoria compartida de Codex/Claude/Cursor/Grok: `C:\dev\.ai\memoria`.

## Hecho (2026-11-10, claude-code — primeras órdenes paper reales)
- El plan de las 18:00 del 09-11 **no corrió**: las tareas llamaban `powershell.exe` sin ruta y no está en el PATH
  (`0x80070002`); `chequeo` solo ve que estén registradas. Ahora usan la ruta completa de System32 y `-WindowStyle Hidden`;
  `schedule-run-daily.ps1` registra igual.
- 14:42 (Puebla): plan y execute desde el Programador. 10 compras aprobadas por el pretrade, todas `SKIPPED no_midpoint`:
  sin suscripción a datos de mercado, IBKR da el error 354. Arreglo: `market_data_type_for("paper_orders")` = 3
  (diferidos si no hay suscripción); live sigue en 1. Freeze sin cambios.
- 14:49–14:50: 10 órdenes LMT `ibt-20261109-*` enviadas. Llenadas BIL 109 @91.50, PDBC 541 @18.33, TIP 94 @105.30,
  GLD 23 @369.66 y VWO 176 @56.48, a ≤3 pb del medio. TLT, VEA, VNQ, IEF y SPY caducaron al cierre. Comisiones y tasas ≈6.71 USD.
  Al cierre: NetLiq 999,977 USD, efectivo 951,762.
- **El execute murió a las 14:57:51 con `0xC000013A`** (consola cerrada o Ctrl+C; la ventana era visible). No escaló a
  Adaptive, no hizo `reconcile_after`, no guardó el libro y `reports/daily/2026-11-09-execute.json` sigue siendo el de 14:42.
  **Corrección (11-11):** no era cierto que «el libro sale del broker»: el primer execute de las 14:42 guardó
  `paper_account.json` con 0 acciones; con 5 en el broker habría activado el kill switch. Apartado en
  `data/logs/paper_account.broker0-20261110.json`.
- Sin datos en vivo, el límite usa el medio diferido 15 min. Vale para paper; para dinero real hacen falta datos en vivo.

## Hecho (2026-11-11, claude-code — segunda tanda de la rampa)
- Laptop dormida o apagada: no corrieron el plan de las 18:00 ni el execute de las 9:05. Al encenderla, a las 10:08, los dos
  arrancaron solos (StartWhenAvailable) y murieron en segundos con `0xC000013A` sin escribir log. **Causa sin encontrar.**
  Lanzados a mano con `Start-ScheduledTask`, funcionaron.
- Plan 10:16, run_date 2026-11-10, libro tomado del broker: 8 compras ≈10k USD. Execute: 8/8 llenadas, 4 con límite y 4 tras
  escalar a Adaptive; slippage −2.0 a +9.3 pb contra el medio. Comisiones y tasas ≈9.73 USD. NetLiq 1,000,253 USD,
  efectivo 872,076, 10 ETF en cartera; libro = broker.
- El execute salió con código 2 al final: `Path.rename` falla en Windows si el destino existe (`pending_orders.done.json`
  del día anterior). Ahora usa `replace` en los tres sitios (`run_daily.py`), con prueba. Se perdió solo
  `reports/daily/2026-11-10-execute.json`; órdenes, libro y slippage sí quedaron. Pending de hoy archivado a mano en `.done.json`.
- **Decisión de Adam (11-11):** unos 6 meses de paper antes de dinero real. Claude no envía órdenes reales ni activa live
  (Adam pidió mover 5 USD reales: rechazado). Al terminar el periodo, Claude prepara un script de paso a live con
  verificaciones (cuenta U…, puerto 4001, freeze, chequeo); Adam lo ejecuta y da el login/2FA.

## Hecho (2026-11-09 tarde, claude-code — paso a órdenes en paper, con el sí directo de Adam)
- `.env`: `EXECUTION__MODE=paper_orders`, `TRADING__ALLOW_BROKER_ORDERS=true`, `IB__EXPECTED_ACCOUNT=DU…26`; `MODE` sigue
  PAPER. Freeze re-congelado: hash `31285ba17f3bcf14`. `chequeo`: `listo_paper=true`, `permiso_ordenes=true`.
- **Libro de sombra apartado** a `data/logs/paper_account.shadow-20261109.json` y `paper_equity.shadow-20261109.jsonl`.
  Con 9 posiciones ficticias contra 0 en el broker, `reconcile_before` habría activado el kill switch en la primera
  ejecución; `PAPER-OPS.md` no lo menciona. Sin libro, el plan inicializa desde el broker (necesita el Gateway abierto).
- Ninguna orden a mano. Flujo: plan 18:00 hoy → ejecución 09:05 mañana (hora de Puebla).
- 09-11 15:10: Adam desmarcó «API de solo lectura» y activó el reinicio diario del Gateway (23:45). `chequeo` con
  what-if real: `listo_paper=true`, `permiso_ordenes=true`, 0 órdenes abiertas. Tareas `plan`, `execute` y `heartbeat`:
  corren en batería, despiertan el equipo y arrancan al estar disponibles; `schedule-run-daily.ps1` lo reaplica al registrar.
- **Antes de la primera ejecución**: `plan` nunca ha corrido (0x41303) y `execute` dio 0x800710E0; ver
  `data/logs/ibtrader-run-daily-plan.log` tras las 18:00.
- **Escala en paper (Adam, 09-11: «vamos escalando»)**: se deja `max_order_notional_usd`=10,000 sin re-congelar. El recorte
  ya es la rampa: máximo 10k por ETF y sesión, y `settled_after` sigue comprando hasta el objetivo. Subir el tope solo
  tras una semana con ejecuciones y conciliación limpias, porque re-congela y reinicia el conteo de paper. Tamaño real: sin definir.
- **Trampa pytest**: no hay `conftest` que bloquee la red y `.env` ya permite órdenes. Correr la suite con
  `$env:EXECUTION__MODE='shadow'; $env:TRADING__ALLOW_BROKER_ORDERS='false'`.

## Hecho (2026-11-09, claude-code — primera conexión a la cuenta paper y estudio de apalancamiento)
- IB Gateway en simulado, puerto 4002, API solo lectura **a propósito** (el sistema sigue en sombra). Sin órdenes;
  sin tocar `.env`, freeze ni tareas.
- `ib_readonly_check.py`: cuenta paper confirmada (DU…26, INDIVIDUAL), 0 posiciones, **NetLiquidation y efectivo
  0.00 USD** a las 15:56 UTC. **Actualización 18:48 UTC, tras reabrir el Gateway: 1,000,000.00 USD**, 0 posiciones,
  poder de compra 4,000,000; `chequeo` con `cuenta_ibkr=true`, `listo_paper=true`, sin pendientes. Ojo: el Gateway dejó
  de estar abierto entre las 15:56 y las 17:46 UTC (causa sin confirmar), y `cuenta_ibkr` imprime el número de cuenta completo.
- Trampa: los primeros minutos tras abrir el Gateway, cuenta y posiciones expiran («request timed out») y el script
  imprime `positions: 0, cash_usd: null` con exit 0. Ese 0 no es dato; repetir hasta que `cash_usd` no sea null.
- `ibtrader chequeo`: `listo_sombra=true`, `listo_paper=true`, sin pendientes. Pero `gateway_ibkr` solo prueba el
  puerto TCP (`preflight.py:149`): dio `true` con la cuenta sin responder y con saldo 0.
- `research-leverage` 1.0/1.25/1.5, universo 10 ETF, ventana 2016-10/11 → 2026-11-06, `ENGINE__HISTORY_DAYS=4400` y
  tasa por variable de proceso. Mejor configuración (`ewmac_hrp`), CAGR / vol / Sharpe / max DD:
  1.0× 6,07 % / 6,69 % / 0,915 / −11,0 %; a 6 %: 1.25× 6,42 / 7,97 / 0,821 / −11,9, 1.5× 6,42 / 9,04 / 0,733 / −14,3;
  a 4 %: 1.25× 6,77 / 7,97 / 0,862 / −11,8, 1.5× 7,10 / 9,04 / 0,805 / −13,9. En las 3 configuraciones el Sharpe baja
  con cada nivel de apalancamiento y a ambas tasas. Tasa constante: la real varió. 925 vetos de exposición en la
  corrida a 6 %, sin separar por nivel.
- **Corrección a lo de abajo («hold-out 2024-11-08 sin abrir»)**: no se registró apertura formal, pero ya hay corridas
  sin hold-out hasta 2026-11 sobre las mismas configuraciones (`portfolio_minimo*-20261108`, `20261108T05*`). Ese
  tramo ya no es dato virgen para ellas.

## Hecho (2026-11-07, claude-code — conexión Tiingo e IBKR)
- Tiingo: token en `.env` (`DATA__TIINGO_TOKEN`, ignorado por `.gitignore:15`, nunca en git). Probado:
  `/tiingo/daily/SPY` responde OK (historia 1993-01-29 → 2026-11-06).
- IB Gateway 10.50 Stable instalado (firma válida de Interactive Brokers) en
  `%LOCALAPPDATA%\Programs\ibgateway\ibgateway.exe`. Todavía sin configurar la API: esa configuración se guarda
  por usuario después de iniciar sesión.
- Cuenta IBKR: solicitud «En curso», falta «Pending Document Upload». **No hay cuenta paper (DU…)**: IBKR la
  habilita al aprobar la cuenta (Settings > Paper Trading Account).
- Al existir la paper: entrar a Gateway en modo Paper → Configure > Settings > API > Settings: Socket Clients on,
  puerto 4002 (`IB__PAPER_PORT`), solo localhost on, Read-Only off (el sistema manda órdenes a paper).
- 08-11: solicitud con formularios completos; falta que IBKR valide el domicilio y acredite el primer depósito.
- Puerta IA: proyecto `ibkr` (Haiku 5.5, 5 USD/mes), token en `C:\dev\secrets\puerta-ia\ibkr.token`.
  **`ANTHROPIC_*` no pueden ir en `.env`**: `AppSettings` prohíbe claves extra y todo el CLI truena. Pasarlas al
  proceso (ver cómo en la prueba del copiloto). Extra `.[ai]` instalado en el venv (faltaba: `sdk_missing`).
- `.env`: `DATA__TIINGO_TOKEN`, `OPS__COPILOT=true`, `OPS__AI_MODEL=claude-haiku-5-5`. `copilot-research` probado
  por la puerta: 1 hipótesis, US$0.006.
- 08-11, con el sí directo de Adam: `.env` con `STRATEGY__NAME=pipeline` y universo de 10 ETF (elegido en sombra; el
  pipeline aún no pasa compuertas con datos reales). Freeze re-congelado (hash `661b3d57407b55b9`).
- Tareas registradas con `run-task.ps1`, hora local de Puebla (UTC-6 todo el año): `ibtrader-run-daily-execute`
  09:05 L-V, `ibtrader-heartbeat-check` 12:00 Ma-S, `ibtrader-run-daily-plan` 18:00 L-V. `ibtrader-autopilot` y
  `ibtrader-paper-reconcile` siguen sin tocar y sin `run-task.ps1`.
- `ibtrader chequeo`: `listo_sombra=true`; `listo_paper=false` solo por `gateway_ibkr`. Al haber cuenta paper,
  probar con `scripts\ib_readonly_check.py`.
- 08-11, investigación con historia larga (`ENGINE__HISTORY_DAYS`, no `DATA__…`; default 5 años):
  `config/universe-10etf-largo.json` (DBC por PDBC, solo investigación) desde 2006, hold-out 2024-11-08 sin abrir:
  0 PASS; mejor `static_box_risk_parity` SR 0,81, t 3,23, DSR 0,992, pct 76,7, no gana al 60/40 (SR 1,03).
  Ledger en 45 ensayos. Trampa: la caché quedó con 20 años y sirve de más aunque se pidan menos, así que
  `minimo-20261108` (SR 0,91 static) cubre 2006–2026, no 2014–2026: **no es comparable** con `20261108T050413Z`.

## Hecho (2026-10-26, claude-code — los cinco pendientes de la revisión)
- `short_only`: el runner armaba un sistema long-only que el motor short-only anulaba (cero operaciones).
  Ahora `SystemConfig.short_only` (excluyente con `long_only`) recorta a ≤ 0 y el runner lo mapea desde
  `TRADING__DIRECTION`.
- Tope de apalancamiento: ya no reescala todo el renglón; solo se escalan los símbolos cuya posición cambió ese
  día. Antes 43 % de los cambios de peso (989/2318) ocurrían sin que la posición del símbolo cambiara; ahora 0.
- Benchmarks en la ventana exacta de la candidata (`start=warmup_end`); un ETF sin precio en la primera barra se
  excluye de todos los benchmarks con aviso (`excluded_symbols`, `note`) en vez de mover la ventana.
- Sesión del simulador con calendario NYSE: feriados (incl. Viernes Santo, Juneteenth, regla de Año Nuevo en
  sábado), cierres a las 13:00 y cierres especiales (2025-01-09 Carter, etc.). Probado contra 2024–2027.
- Vol target: con `max_leverage=1.0` el sistema pide 10 % y entrega ~6,6–6,9 % (el tope ata 43–49 % de los días,
  datos sintéticos). Documentado en `SystemConfig`; `research-portfolio` reporta `vol_target`
  (pedido, realizado = objetivo efectivo, fracción de días con tope, `shortfall`). **No se subió el apalancamiento**:
  llegar a 10 % pide ~1,5× con margen, decisión de Adam.

## Hecho (2026-10-25 noche, claude-code — revisión y arreglo de lo de Cursor 23–25 oct)
- **CI**: estuvo roja del 24-10 (`7eabf12`) al 25-10 (`6a5bc12`): 20 corridas fallidas + 5 canceladas, todas
  en `ruff`, así que mypy y pytest **no corrieron en CI** en ese tramo. Arreglado: ruff 0 errores, mypy limpio
  (97 archivos), pytest offline 511 pasan (red bloqueada, 0 conexiones). La primera corrida con lint verde
  (40273486757) destapó lo que la CI roja escondía: `test_portfolio_runner_cli.py` importa `tests.…` y con el
  `pytest` plano de CI no se podía importar → `pythonpath = ["."]` en `pyproject.toml` (`d56bf3d`).
  **CI verde** en `d56bf3d`: corrida 40274125812, 4/4 jobs (lint+types+tests y CLI smoke, ubuntu y macOS).
- **Investigación (`94a3a6c`)**:
  - Escalar de forecast sin `bfill` (look-ahead de hasta 500 barras en la ventana evaluada); `warmup_end`
    espera a un escalar point-in-time.
  - Pesos de instrumento = riesgo: cajas `b_k/n_k` sin `1/σ`, HRP sobre `r_t/σ_{t-1}` (antes IEF cargaba
    35–58 % del riesgo). `box_inverse_vol` → `box_risk_parity` (alias).
  - `research-portfolio`: t ≥ 3, DSR ≥ 0,95 sobre todos los trials (ledger `reports/research/portfolio_trials.jsonl`),
    PBO < 0,5, percentil ≥ 95 vs carteras aleatorias, hold-out obligatorio, selección por DSR.
    Paseos aleatorios (semillas 7/11/23, grid completo): gates viejos pasaban 6/9 y 9/9; ahora 0/9.
  - Motor modo peso reintenta tras veto; costos OOS sin las órdenes del calentamiento.
- **Paper (`9a1eb78`)**: curva = caja + acciones × precio (`data/paper_account.json`) o NAV del broker
  (`paper-equity --append`); alertas de «matar» por DD apagadas hasta 20 días de equity real. Freeze schema 2
  (mode/trading/strategy), nunca se auto-escribe, `--write` no re-baselina sin `--force`. Orden de ejemplo
  fuera de `data/`. Brief IA sin `temperature` y solo por la puerta (`--use-ai` sin puerta sale 2).
  Simulador: LMT envejecida no cruza su límite; semilla 0 por defecto.
- **Repo (`e543123`)**: `.ai/drafts` (194) y `data/paper_*.json` fuera del índice.
- Freeze local reescrito a schema 2 (misma config, hash `1658a22e075133ca`); no se tocaron las tareas programadas.

## Corrección a lo que decía este RELEVO (Cursor, 25-10)
- «expectancy −$1886/trade» **engañaba**: es el promedio de solo 16 trades cerrados del OOS cosido y no cuenta la
  posición abierta. El fold 3 da expectancy −$2034 con P&L +$2,7k. Lo que vale es el P&L de la curva:
  OOS cosido CAGR ~3,4 %, Sharpe ~0,49 contra comprar y mantener 15,1 % / 0,94. La conclusión no cambia: el SMA
  sobre SPY pierde contra B&H; no retocar params con este OOS.

## A medias / pendiente
- `ibtrader-ibc-check` (08:00) solo imprime una lista fija que nadie ve: se puede quitar
  (`pwsh -File scripts/schedule-ibc-check.ps1 -Action Unregister`). Autopilot y reconcile: inofensivos (0 órdenes).
- El paper sigue sobre el motor viejo SMA/SPY; nada de fase 2 ha pasado gates con datos reales (no hay corridas).
- Cierres especiales futuros (duelo nacional, etc.) hay que agregarlos a mano en `SPECIAL_CLOSURES`.
- `research-portfolio --profile full` tarda ~6–8 min por corrida de 9 configuraciones.

## Adam
1. Tiingo + `RESEARCH__HOLDOUT_START` (sin hold-out declarado, `research-portfolio` siempre da FAIL).
2. Para medir paper de verdad: `data/paper_account.json` con `{"cash": …, "shares": {…}}` o
   `ibtrader paper-equity --append <NAV>` cada día.
3. Meses paper congelado.
4. Decidir si el objetivo de vol es el efectivo (~6–7 % sin margen) o se pide margen para `max_leverage` 1,5×.

## No tocar
- Solo main. Cero LIVE. No curve-fit al último fold. No re-baselinar el freeze para «arreglar» una alerta.
