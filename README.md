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
   - Motor de decisiones (fase 1, NO_TRADE): `ibtrader paper-run`
   - Kill switch: `ibtrader kill` / limpiar: `ibtrader clear-kill`

Ejecución LIVE (deshabilitada por defecto):
- Requiere `MODE=LIVE` y `LIVE_TRADING_CONFIRMED=yes` más verificación de puerto y (opcional) cuenta esperada. Si cualquier chequeo falla, se rechaza.

Calidad:
- Lint: ruff; Tipos: mypy; Tests: pytest. CI ejecuta los tres. Los tests no dependen de una conexión IBKR.

CI (GitHub Actions):
- PRs contra `dev` ejecutan lint + mypy + tests.

