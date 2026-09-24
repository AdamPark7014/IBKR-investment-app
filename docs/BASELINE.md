### Baseline oficial — Fase 1 (SMA 10/30 sobre SPY)

Fuente y reproducción:
- Rama/commit: `cursor/ibkr-algo-trader-35c8 @ 32f2686`
- Entorno: Windows 11, Python 3.12, venv limpio, `pip install -e ".[dev]"`
- Comandos: `ibtrader download-data` luego `ibtrader backtest-sample`
- Periodo: 2021-09-27 a 2026-09-23
- Universo: SPY (benchmark SPY)
- Costes: comisión IBKR fija $0.005/acción (mín. $1 por orden), slippage 1bp

Resultados (honestos, SPY solamente):
- Estrategia SMA 10/30 (long/flat implícito del reporte original):
  - CAGR: 0.43%
  - Sharpe: 0.11
  - Sortino: 0.15
  - Máx Drawdown: -27.2%
  - Retorno total: +2.2%
  - Fills: 410
  - Días long: 797 / short: 427 / flat: 29
- Buy&Hold SPY:
  - CAGR: 11.7%
  - Sharpe: 0.73
  - Máx Drawdown: -25.4%

Observación: la estrategia underperforma fuertemente a Buy&Hold en este periodo, con alto churn. Este baseline sirve como referencia para Evolution Engine V2; cualquier cambio debe compararse OOS vs este baseline, no in-sample.

Datos:
- Archivo JSON con métricas: ver `baselines/phase1_sma_spy_20210927_20260923.json`

