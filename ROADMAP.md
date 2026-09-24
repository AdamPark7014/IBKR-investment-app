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

Fase 2:
- Conectores adicionales: fundamentales (IBKR/EDGAR), macro (FRED), sentimiento/noticias (interfaces).
- Portfolio manager avanzado: riesgo por sector/factor, límites regulatorios, beta/alpha tracking, risk parity robusto, mean-variance con límites.
- Observabilidad: servicio API (FastAPI) y dashboard (frontend) con señales, decisiones, portafolio, riesgo y PnL.
- Simulaciones de robustez: Monte Carlo/bootstrap, análisis de sensibilidad de parámetros, informes de walk-forward.

Fase 3:
- Ejecución semiautónoma LIVE (con aprobación humana), órdenes compuestas/bracket, monitor de fills y reconciliación.
- Anti-bias engine y post-mortems automatizados con memoria estructurada.
- Integración con colas (Redis) y almacenamiento perenne (PostgreSQL) para producción.

Definición de hecho:
- Lint y type-check en verde; cobertura razonable de tests; documentación clara; sin datos inventados; fallos manejados con seguridad; “NO_TRADE” ante ambigüedad.

