### IBKR Investment System (institucional, fase 1)

Sistema cuantitativo profesional con ejecución por IBKR. Papel por defecto; LIVE requiere confirmación explícita y verificaciones. Este repo sigue el SPEC "INSTITUTIONAL AI INVESTMENT SYSTEM — IBKR".

Documentación principal:
- `ARCHITECTURE.md`: arquitectura modular y capas.
- `DATA_SOURCES.md`: qué provee IBKR vs fuentes externas, licencias.
- `RISK_MODEL.md`: límites, circuit breaker, "NO_TRADE".
- `DECISION_ENGINE.md`: motor de decisiones (fase 1), journal, explicabilidad.
- `ROADMAP.md`: plan por fases y definición de hecho.

Advertencia honesta:
- Ningún sistema compra el mínimo ni vende el máximo de forma fiable. El objetivo es valor esperado positivo con drawdowns controlados, validado fuera de muestra y en paper antes de cualquier dinero real.

Requisitos (Windows 11, Python 3.12):
1) Instalar Python 3.12 (x64) y Git.
2) Instalar IB Gateway (o TWS), habilitar API.
   - Gateway: Configuración API → "Read-Only API" desactivado para trading; puerto: Paper 4002, Live 4001; permitir 127.0.0.1.
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
   - Motor de papel (BUY/SELL/WATCH/NO_TRADE, sin órdenes): `ibtrader paper-run`
   - Reconciliación paper (desired vs `data/paper_positions.json`, JSON a stdout, cero órdenes): `ibtrader paper-reconcile`. Fase 3 = cimiento disciplinado (drift + slippage ledger opcional); **no LIVE**. El playbook institucional excluye LLM sobre titulares, alt-data de pago e intradía — aquí solo comparas cartera objetivo vs held.
   - Paper stack (desired/held/drift en SQLite, JSON a stdout, cero órdenes): `ibtrader paper-stack`
   - Slippage report (resumen del ledger, JSON, cero órdenes): `ibtrader slippage-report`
   - Paper vs OOS (compara curva paper vs hold-out, JSON, cero órdenes): `ibtrader paper-vs-oos`
   - Congelar/verificar config paper (JSON, cero órdenes): `ibtrader config-freeze` (`--write` una vez; default `--verify`). Freeze en `data/paper_config_freeze.json`.
   - Autopilot (backend pesado + UI de una pantalla, cero órdenes): ibtrader autopilot · opcional --use-ai via puerta IA (pocos tokens sobre JSON ya comprimido; sin noticias).
   - Schedule diario (Task Scheduler, paper triage only, 0 órdenes, no LIVE):
     - Registrar tarea `ibtrader-autopilot` (16:30 local por defecto): `pwsh -File scripts/schedule-autopilot.ps1 -Action Register`
     - Opcional hora: `-Time 17:00`. Estado: `-Action Status`. Quitar: `-Action Unregister`.
     - Registrar tarea `ibtrader-paper-reconcile` (16:35 local, tras autopilot): `pwsh -File scripts/schedule-reconcile.ps1 -Action Register`
     - Estado/quitar/hora: mismos `-Action Status|Unregister` y `-Time` que autopilot.
     - Registrar tarea `ibtrader-ibc-check` (08:00 local): `pwsh -File scripts/schedule-ibc-check.ps1 -Action Register`
     - Estado/quitar/horas/RunOnce: mismos `-Action Status|Unregister|RunOnce` y `-Time` (default 08:00).
     - Register-all (las 3 tareas a la vez; defaults 16:30 / 16:35 / 08:00): `pwsh -File scripts/schedule-register-all.ps1 -Action Register`
     - Estado/quitar/horas: `-Action Status|Unregister`; opcionales `-AutopilotTime` `-ReconcileTime` `-IbcTime`.
     - Smoke paper triage (Status de las 3 tareas; RunOnce: ibc-checklist → paper-reconcile → paper-vs-oos → paper-stack; 0 órdenes, no LIVE): `pwsh -File scripts/ops-smoke.ps1` / `-Action RunOnce`
     - Estado por defecto no falla si alguna tarea no está registrada.
   - Checklist Gateway/IBC (JSON manual, no instala nada): `ibtrader ibc-checklist`
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
  - Stooq: