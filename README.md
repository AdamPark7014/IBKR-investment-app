### IBKR Investment System (institucional, fase 1)

Sistema cuantitativo profesional con ejecución por IBKR. Papel por defecto; LIVE requiere confirmación explícita y verificaciones. Este repo sigue el SPEC “INSTITUTIONAL AI INVESTMENT SYSTEM — IBKR”.

Documentación principal:
- `ARCHITECTURE.md`: arquitectura modular y capas.
- `DATA_SOURCES.md`: qué provee IBKR vs fuentes externas, licencias.
- `RISK_MODEL.md`: límites, circuit breaker, “NO_TRADE”.
- `DECISION_ENGINE.md`: motor de decisiones (fase 1), journal, explicabilidad.
- `ROADMAP.md`: plan por fases y definición de hecho.

Advertencia honesta:
- Ningún sistema compra el mínimo ni vende el máximo de forma fiable. El objetivo es valor esperado positivo con drawdowns controlados, validado fuera de muestra y en paper antes de cualquier dinero real.

Requisitos (Windows 11, Python 3.12):
1) Instalar Python 3.12 (x64) y Git.
2) Instalar IB Gateway (o TWS), habilitar API.
   - Gateway: Configuración API → “Read-Only API” desactivado para trading; puerto: Paper 4002, Live 4001; permitir 127.0.0.1.
3) Crear/activar entorno virtual:
   - PowerShell:
     ```powershell
     py -3.12 -m venv .venv
     .\\.venv\\Scripts\\Activate.ps1
     pip install -e .[dev]
     ```
4) Configuración `.env` (copiar `.env.example` a `.env` y ajustar):
   - `MODE=PAPER`
   - `IB_HOST=127.0.0.1`, `IB_PORT_PAPER=4002`, `IB_PORT_LIVE=4001`
   - `LIVE_TRADING_CONFIRMED=no`
   - `IB_EXPECTED_ACCOUNT=` (opcional para verificación extra en LIVE)
5) Primeros comandos:
   - Estado: `ibtrader status`
   - Descargar datos (yfinance, para backtest): `ibtrader download-data`
   - Backtest de muestra (SMA crossover): `ibtrader backtest-sample`
     - Puedes generar un ID de experimento: `ibtrader backtest-sample --exp-id p1p5_check`
     - Comparar modos (P5): `ibtrader compare-directions --exp-id p1p5_compare`
   - Motor de decisiones (fase 1, NO_TRADE): `ibtrader paper-run`
   - Kill switch: `ibtrader kill` / limpiar: `ibtrader clear-kill`

Ejecución LIVE (deshabilitada por defecto):
- Requiere `MODE=LIVE` y `LIVE_TRADING_CONFIRMED=yes` más verificación de puerto y (opcional) cuenta esperada. Si cualquier chequeo falla, se rechaza.

Calidad:
- Lint: ruff; Tipos: mypy; Tests: pytest. CI ejecuta los tres. Los tests no dependen de una conexión IBKR.

CI (GitHub Actions):
- PRs contra `dev` ejecutan lint + mypy + tests.

Datos (P2):
- Todos los comandos (`download-data`, `backtest-sample`, `compare-directions`) usan un pipeline de proveedores con puerta de calidad:
  - Primero Yahoo Finance (vía yfinance 1.x) y, si falla, Stooq CSV con cabeceras tipo `curl` (evita 404).
  - Validación estricta: índice creciente sin duplicados, columnas no vacías. Si falla, se bloquea el backtest.
  - Stooq: en la práctica NO funcional (JS bot-check frecuente). Se mantiene como fallback “best effort”, pero no confiar en él. El error agrega la razón de cada proveedor probado.
  - Yahoo Finance (yfinance 1.x) es la única fuente gratuita funcional por defecto.
  - IBKRProvider (vía `ib_async`) está implementado para históricos diarios (TRADES). Es opcional y seleccionable vía `DATA__PROVIDERS` (por defecto `yahoo,stooq`), y requiere IB Gateway/TWS local con API habilitada.

Histeresis costo-aware (P3–P4):
- Opcional y desactivada por defecto. Variables:
  - `TRADING__BENEFIT_BPS`: beneficio esperado por rebalanceo (bps).
  - `TRADING__RISK_COST_BPS`: coste de riesgo por rebalanceo (bps).
- Si cualquiera > 0: solo reequilibra si `beneficio_esperado > comisión + slippage + coste_riesgo`. Entradas iniciales, salidas totales y flips de signo no se bloquean por histeresis (se aplica a micro-rebalances).
- Razones de NO_REBALANCE se registran en logs estructurados (JSON).

BacktestSkeptic:
- El CLI señalará resultados “sospechosos” (e.g., Sharpe > 3 o CAGR > 100%) vía `skeptic_flags` en la salida para evitar falsas conclusiones por datos corruptos o fugas.

V2 Fase P6–P9 (comandos reproducibles)
- P6 Régimen (aprendido, no hardcodeado): GMM sobre [ret_1d, vol_20] del benchmark.
  - `ibtrader regime-fit --n-components 2 --exp-id p6_regime`
  - Salida: `reports/regime_<exp-id>.csv`, conteos por régimen, medias por componente.
- P7 Validación de señales (SMA): CV con purga/embargo y comparación con B&H.
  - `ibtrader signal-validate --direction long_only --exp-id p7_sig`
  - Salida: métricas por fold y agregadas; B&H de referencia.
- P8 Riesgo integrado: veto de régimen + sizing por objetivo de volatilidad (anual) y límites.
  - `ibtrader run-with-risk --risk-on-threshold 0.5 --exp-id p8_risk`
  - Respeta `RISK__TARGET_VOL_ANNUAL`, `RISK__RISK_ON_THRESHOLD`, `RISK`* límites. No envía órdenes.
- P9 Walk-Forward (train/validate/test por tiempo, parámetros congelados):
  - `ibtrader walk-forward --exp-id p9_wf`
  - Salida: `in_sample`, `validation`, `oos` (OOS nunca usado para tuning) y B&H OOS.

