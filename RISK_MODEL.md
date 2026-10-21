### Modelo de riesgo (fase 1)

Objetivo: preservar capital y evitar pérdidas catastróficas. El Riesgo manda y puede bloquear cualquier orden.

Límites duros (en `src/ibtrader/risk/manager.py`):
- Máximo tamaño por posición: % de equity (notional).
- Máxima exposición total: % de equity (suma de nocionales absolutos).
- Límite de pérdida diaria: si el equity cae por debajo del umbral desde la apertura del día, se detiene el trading.
- Máximo de órdenes por día: evita ráfagas y efectos no deseados.
- Whitelist de símbolos permitidos.
- Kill switch: archivo bandera que fuerza STOP TRADING de inmediato.
- Circuit breaker: si cualquier validación crítica falla (datos corruptos, conexión IBKR inestable, precios inconsistentes, spread excesivo, liquidez insuficiente, etc.), se sale por la vía “NO_TRADE” y se requiere intervención humana.

Defaults de `RiskConfig` (`src/ibtrader/config.py`). Se cambian por variables `RISK__*` en `.env` (prefijo `RISK__`, ver `.env.example`):

| Límite | Default | Variable `.env` | Efecto al superarlo |
|---|---|---|---|
| Pérdida diaria | 5 % del equity al abrir el día | `RISK__DAILY_LOSS_LIMIT_PCT=5` | Halt del día (y del siguiente si se detecta al cierre): bloquea aperturas/aumentos; salidas permitidas |
| Pérdida acumulada | 20 % vs. equity inicial | `RISK__CUMULATIVE_LOSS_LIMIT_PCT=20` | Estado RESTRICTED: bloquea aperturas/aumentos |
| Drawdown desde el pico | 20 % | `RISK__DRAWDOWN_LIMIT_PCT=20` | Estado RESTRICTED: bloquea aperturas/aumentos |
| Volatilidad objetivo | 10 % anual | `RISK__TARGET_VOL_ANNUAL=0.10` | Escala el tamaño de posición (no bloquea) |

Fail-closed: si el chequeo de pérdida diaria al cierre (`update_equity`) lanza una excepción, el gestor queda bloqueado para el día siguiente (`halt_next_day`) y lo registra en el log; las reducciones y cierres siguen permitidos. El backtest expone por barra si el gestor habría bloqueado exposición nueva (`BacktestResult.restricted`); el walk-forward y los runners de research lo resumen como `restricted_bar_frac` en las stats OOS.

“NO TRADE” (reglas explícitas, ver SPEC):
- Datos insuficientes, alta incertidumbre, spread/impacto demasiado alto, liquidez insuficiente, riesgo alto, tesis contradictoria, valoración extrema sin catalizador, régimen no permitido, anomalías de datos, conexión IBKR inestable.

Semántica de Kill Switch (archivo `data/KILL_SWITCH`):
- Modo por defecto: `flatten` (documentado en `RiskConfig.killswitch_action`). Cuando el archivo existe:
  - Se liquidan posiciones existentes en la siguiente apertura (emergency exit).
  - Se bloquean nuevas aperturas y aumentos.
  - Las reducciones y cierres siempre están permitidos.
- Alternativa configurable: `block_new_only`, que bloquea nuevas aperturas/aumentos pero NO fuerza liquidación automática. En ambos modos, las salidas (reduce/cierre/stop/emergency) nunca se bloquean.

Gestión de stops:
- `stop_loss_per_position_pct` (en `RiskConfig`): salida forzada por instrumento, ejecutada en la siguiente apertura cuando el precio cruza el umbral vs. precio medio de la posición.
- Tipos de salida (a documentar en el journal): tesis, valoración, riesgo, técnico, portafolio. Los forced exits se etiquetan explícitamente como `stop_loss` o `kill_switch`.

Auditoría:
- Toda decisión (incluyendo “NO_TRADE”) se registra en SQLite con timestamp, parámetros, evaluación de riesgo y motivo.
- Cada métrica/entrada de datos indica fuente y timestamp de ingesta.

Futuras extensiones:
- Límites por sector/industria y límites de concentración por emisor.
- Presupuestos de riesgo por factor (beta, momentum, value, quality).
- VaR/CVaR con colas gordas, simulación de estrés y “what-if”.
- Evaluaciones de liquidez/impacto basadas en volumen y spread en vivo.

