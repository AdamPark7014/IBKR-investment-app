### BASELINE_REPORT — Fase 1 (SMA 10/30 sobre SPY)

Este documento preserva el baseline REAL, sin alteraciones, para comparar toda evolución futura (V2) estrictamente fuera de muestra.

Ejecución (propietario):
- Branch/commit: `cursor/ibkr-algo-trader-35c8 @ 32f2686`
- Windows 11, Python 3.12, venv limpio
- Instalación: `pip install -e ".[dev]"`
- Comandos: `ibtrader download-data` y luego `ibtrader backtest-sample`
- Periodo: 2021-09-27 a 2026-09-23
- Universo: SPY (benchmark SPY)
- Costes: comisión fija IBKR $0.005/sh (mín $1), slippage 1bp
- HTML reproducible: `reports/sample_backtest.html` (generado localmente)

Resultados (copiados del run real):
- Estrategia SMA 10/30 (short habilitado en ese run):
  - CAGR: 0.004349060450075104
  - Sharpe: 0.1112034889540013
  - Sortino: 0.14991858161642665
  - Máx Drawdown: -0.27155142547360467
  - Retorno total: 0.02181208784033073
  - Fills: 410
  - Días long: 797 / SHORT: 427 / flat: 29
- Buy&Hold SPY:
  - CAGR: 0.1171407252215686
  - Sharpe: 0.7289258234489157
  - Máx Drawdown: -0.25360573583036894

Métricas derivadas (calculadas a partir de los valores anteriores, sin alterar los insumos):
- Calmar ≈ 0.004349 / 0.271551 ≈ 0.0160
- Recovery Factor ≈ 0.021812 / 0.271551 ≈ 0.0803
- Exposición por estado (fracciones): long ≈ 797/1253 ≈ 0.636; short ≈ 0.341; flat ≈ 0.023
- Volatilidad (diaria, reporte original): 0.1710 (solo informativa)
-- Profit factor, expectancy, turnover y costes totales no fueron impresos en ese run; el sistema ahora los calcula al ejecutar `ibtrader backtest-sample` (ver CLI), pero este baseline preserva intactos los números originales del propietario.

JSON del baseline:
- `baselines/phase1_sma_spy_20210927_20260923.json`

Conclusión honesta:
- La estrategia underperforma de forma marcada al benchmark (Buy&Hold SPY) en el periodo analizado. Este baseline será la vara de medición para V2; toda mejora debe demostrarse OOS/Nueva corrida y no solo in-sample.

