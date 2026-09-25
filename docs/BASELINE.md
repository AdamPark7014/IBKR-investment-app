### Baseline oficial — Fase 1 (SMA 10/30 sobre SPY)

Fuente y reproducción:
- Rama/commit: `cursor/ibkr-algo-trader-35c8 @ 32f2686`
- Entorno: Windows 11, Python 3.12, venv limpio, `pip install -e ".[dev]"`
- Comandos: `ibtrader download-data` luego `ibtrader backtest-sample`
- Periodo: 2021-09-27 a 2026-09-23
- Universo: SPY (benchmark SPY)
- Costes: comisión IBKR fija $0.005/acción (mín. $1 por orden), slippage 1bp

Resultados (honestos, SPY solamente):
- Estrategia SMA 10/30 (long+short según el baseline original):
  - CAGR: 0.004349060450075104
  - Sharpe: 0.1112034889540013
  - Sortino: 0.14991858161642665
  - Máx Drawdown: -0.27155142547360467
  - Retorno total: 0.02181208784033073
  - Fills: 410; Comisión total: 440.40
  - Días long: 797 / short: 427 / flat: 29
- Buy&Hold SPY:
  - CAGR: 0.1171407252215686
  - Sharpe: 0.7289258234489157
  - Máx Drawdown: -0.25360573583036894

Observación: la estrategia underperforma fuertemente a Buy&Hold en este periodo, con alto churn. Este baseline sirve como referencia para V2; cualquier cambio debe compararse OOS vs este baseline, no in-sample.

Datos:
- Archivo JSON con métricas: ver `baselines/phase1_sma_spy_20210927_20260923.json`

### P5 — Comparación de direcciones (SPY, ~5 años)

Nota importante: Las siguientes cifras pertenecen a la versión v1.0 (ejecución “mismo bar”) y se mantienen solo como referencia histórica. Han sido SUPERSEDED por v1.1 (ejecución en la apertura del día siguiente). No deben usarse para evaluar la versión actual del motor.

- [SUPERSEDED v1.0] Long only: CAGR 6.29%, Sharpe 0.78, Máx DD -18.5%, Fills 38, Comisión ~$39
- [SUPERSEDED v1.0] Short only: CAGR -5.51%, Sharpe -0.24, Máx DD -31.9%, Fills 405
- [SUPERSEDED v1.0] Long+Short (banda 0.02): CAGR 0.48%, Fills 225, Comisión ~$256
- [Referencia] Buy&Hold SPY: CAGR 11.7%, Sharpe 0.73, Máx DD -25.4%

Notas:
- El modo SHORT permanece deshabilitado por defecto (evidencia negativa).
- La comparación se ejecuta con `ibtrader compare-directions --exp-id p1p5_compare` y reporta métricas extendidas por modo y para Buy&Hold.

Corrección de ejecución (v1.1):
- El backtester ahora ejecuta señales de cierre en la apertura del siguiente día (t+1), con slippage, para evitar look-ahead. El baseline original (v1.0) se preserva tal cual; junto a él se registrará un baseline v1.1 “next-open” ejecutado en la PC del propietario.
- Para reproducir v1.1 y la comparación de direcciones bajo la ejecución corregida:
  - `ibtrader download-data`
  - `ibtrader backtest-sample --exp-id baseline_v11`
  - `ibtrader compare-directions --exp-id p1p5_v11`

Resultados v1.1 (se registrarán oficialmente en la PC del propietario; reproducibles con los comandos anteriores):
- Long only (v1.1): [registrar aquí]
- Short only (v1.1): [registrar aquí]
- Long+Short (v1.1): [registrar aquí]
- Buy&Hold SPY (referencia): [registrar aquí]