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

“NO TRADE” (reglas explícitas, ver SPEC):
- Datos insuficientes, alta incertidumbre, spread/impacto demasiado alto, liquidez insuficiente, riesgo alto, tesis contradictoria, valoración extrema sin catalizador, régimen no permitido, anomalías de datos, conexión IBKR inestable.

Gestión de stops (en `ensemble/combiner.py`):
- Stops y trailing stops basados en ATR como mecanismo técnico estándar.
- Tipos de salida (a documentar en el journal): tesis, valoración, riesgo, técnico, portafolio.

Auditoría:
- Toda decisión (incluyendo “NO_TRADE”) se registra en SQLite con timestamp, parámetros, evaluación de riesgo y motivo.
- Cada métrica/entrada de datos indica fuente y timestamp de ingesta.

Futuras extensiones:
- Límites por sector/industria y límites de concentración por emisor.
- Presupuestos de riesgo por factor (beta, momentum, value, quality).
- VaR/CVaR con colas gordas, simulación de estrés y “what-if”.
- Evaluaciones de liquidez/impacto basadas en volumen y spread en vivo.

