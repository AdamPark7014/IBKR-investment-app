### Roadmap por fases (extracto)

Fase 1 (esta PR):
- Auditoría del repo y rama `dev`; selección de stack (Python 3.12, Pydantic, Typer, pytest, ruff, mypy).
- Documentos: ARCHITECTURE.md, DATA_SOURCES.md, RISK_MODEL.md, DECISION_ENGINE.md, ROADMAP.md.
- Capa de datos con validación/linaje (envelope de DataFrame con metadatos, validadores de integridad).
- Adaptador IBKR (paper) con reconexión; broker simulado para pruebas.
- Risk Manager con circuit breaker (kill-switch, límites duros).
- Journal estructurado (trades y decisiones) en SQLite.
- Esqueleto del Decision Engine (produce “NO_TRADE”).
- Backtesting con separación estricta Train/Val/Test/OOS y reporte básico.
- CI: lint (ruff), type-check (mypy), tests (pytest). Sin dependencia de IBKR en tests.

Fase 2 — Evolution Engine V2 (prioridad absoluta §49 del SPEC):
- A) Data + Feature Store: features versionadas (precio, momentum, tendencia, mean-reversion, volumen, volatilidad, liquidez; interfaces para fundamentales/valoración/macro) con linaje, metodología y validación. Sin fuga temporal.
- B) Regime Engine: bull/bear/sideways, high/low vol, risk-on/off, transición/crisis; la exposición/estrategias/sizing dependen del régimen.
- C) Meta-labeling: capa TAKE/SKIP encima de señales; entrenada con features de régimen/vol/liquidez/señal/fundamentales/macro y rendimiento reciente.
- D) Pronóstico probabilístico: calibración (Brier, log loss), curvas de calibración. No avanzar si no mejora contra baselines OOS.
- E) Sizing dinámico: por edge/confianza/vol/correlación/liquidez/dd/exposición/stop. Comparar vol targeting, fraccional, Kelly fraccional.
- F) Optimización de cartera: restricciones de correlación/sector/factor/beta/liquidez; comparar MV/risk parity/min var/vol targeting con validación OOS.
- G) Salud/deriva de estrategias: decay detector, concept drift, champion vs challenger en sombra.
- H) Ejecución: inteligencia de órdenes, medición de spread/slippage/participación; separar decisión de ejecución.
- I) Auto-auditoría + aprendizaje: post-mortems, atribución y bucle de mejora post-mercado.
- J) Paper trading operacional con gating de riesgo y aprobación humana para LIVE (no avanzar a LIVE sin validaciones).

Fase 3:
- Ejecución semiautónoma LIVE (con aprobación humana), órdenes compuestas/bracket, monitor de fills y reconciliación.
- Anti-bias engine y post-mortems automatizados con memoria estructurada.
- Integración con colas (Redis) y almacenamiento perenne (PostgreSQL) para producción.

Definición de hecho:
- Lint y type-check en verde; cobertura razonable de tests; documentación clara; sin datos inventados; fallos manejados con seguridad; “NO_TRADE” ante ambigüedad.

Notas de auditoría inicial (riesgos de fuga/overfitting):
- Evitar lookahead: separaciones Train/Val/Test/OOS y walk-forward. Purge/embargo en CV temporal (incluido en `ml/cv.py`).
- No comparar y “elegir lo mejor” sobre el mismo periodo; usar champion vs challenger y validación OOS antes de promover.
- Cada métrica en reportes lleva fuente + timestamp + metodología; sin datos inventados. Si una fuente gratuita está bloqueada en el runner (p. ej., yfinance/Stooq), el baseline se genera en el PC del propietario usando `ibtrader backtest-sample`.

