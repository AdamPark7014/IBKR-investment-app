### Arquitectura del sistema (fase 1)

Este repositorio implementa la base de un sistema de inversión cuantitativo y ejecución por IBKR con mentalidad institucional. Se organiza en capas y módulos intercambiables (agentes) y documenta datos, decisiones y riesgos con trazabilidad completa.

Principios:
- Evidencia primero, riesgo controlado, “No trade” es una respuesta válida.
- Papel por defecto; LIVE sólo con confirmación explícita y validaciones múltiples.
- Cada métrica lleva fuente, timestamp y metodología; nunca “se inventa” un dato.
- Tipado y pruebas automatizadas (lint + type check + tests) antes de marcar algo como “hecho”.

Módulos principales (carpeta `src/ibtrader`):
- `config`: configuración tipada (Pydantic), rutas y validaciones de modo PAPER/LIVE.
- `logging`: logging estructurado en JSON para observabilidad.
- `data`:
  - `downloader`: conectores de mercado (fase 1: yfinance para backtest; IBKR para ejecución/monitoring).
  - `cache`: caché local Parquet.
  - `universe`: listas de símbolos.
  - `lineage` (planeado en fase 1): envoltura de DataFrame con metadatos de fuente, timestamp, licencia y metodología.
  - `validators` (fase 1): validaciones de integridad temporal, duplicados, NaNs, timezone.
- `broker`:
  - `base`: interfaz abstracta de broker.
  - `ibkr`: adaptador para IB Gateway/TWS vía API oficial (ib_insync), con reconexión.
  - `simulated`: broker simulado para tests y backtests.
- `strategy`:
  - Interfaz y ejemplos: cruce de medias, mean reversion, rotación cross-sectional.
- `intelligence`:
  - `features`: señales técnicas (tendencia, momentum, volatilidad, volumen, S/R).
  - `regime`: detección de régimen (trend vs range; risk-on/off con VIX y amplitud).
  - (Interfaces para fundamentales/macro a incorporar en fases posteriores).
- `ensemble`: combinación de señales/estrategias con puntuación y filtros de régimen; gestión de stops ATR/trailing.
- `ml`: opción de modelo (Gradient Boosting) con CV temporal purgado y walk-forward (opcional y desactivado por defecto).
- `portfolio`: construcción y sizing (target de volatilidad, risk parity básico, límites de concentración).
- `risk`:
  - `manager`: límites duros (tamaño por posición, exposición, pérdida diaria, contador de órdenes), whitelist, kill-switch y “circuit breaker”.
- `backtest`:
  - `engine`: backtester sin lookahead, comisiones/slippage.
  - `metrics`: estadísticas (CAGR, Sharpe, Sortino, DD, exposición, etc.).
  - `splits` (fase 1): separación estricta TRAIN/VAL/TEST/OOS + walk-forward.
  - `report`: gráficos HTML de equity.
- `execution`:
  - `order`, `portfolio`: normalización de órdenes y utilidades de cartera.
- `ops`:
  - `journal`: bitácora SQLite (trades y decisiones).
  - `status`, `killswitch`.
  - `cli`: CLI Typer para `status`, `download-data`, `backtest`, `paper-run` (sin ejecutar órdenes en esta fase), `kill/clear-kill`.
- `engine/decision` (fase 1): esqueleto del Decision Engine que genera decisiones explicadas y, por política de esta fase, produce acciones “NO_TRADE” (documentadas en el journal).

Diagrama lógico (simplificado):
- DATA (fuente + validación + linaje) → INTELLIGENCE (features/regime + opcional ML) → ENSEMBLE (score y stops) → PORTFOLIO (pesos/limitaciones) → RISK (circuit breaker/ límites) → DECISION (thesis + acción) → (ejecución IBKR en fases posteriores).

Compatibilidad con el SPEC:
- Se respetan las capas y el enfoque multi-agente. En esta fase se crean los puntos de extensión para fundamentales/valoración/macro/noticias, pero se mantienen en “interfaces” o “stubs” para evitar datos inventados.
- La ejecución LIVE permanece bloqueada por diseño y requiere doble confirmación y verificación de cuenta/puerto.

Observabilidad:
- Logging JSON + journal estructurado (SQLite). En fases siguientes: API/servicio de estado y frontend profesional.

Seguridad:
- `.env` (no se comitea). Sin credenciales en el repo. Validaciones de modo LIVE y killswitch.

