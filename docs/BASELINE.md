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

