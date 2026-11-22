# Documentación de IBKR-INVESTMENT-app

Índice único del repo (generado en la limpieza del 2026-11-14). Empieza por el README y el RELEVO.

- Estado y continuidad: [`.ai/RELEVO.md`](../.ai/RELEVO.md)
- Reglas de agentes: [`AGENTS.md`](../AGENTS.md)
- Índice de todos los proyectos: `C:\dev\DOCS.md` · memoria compartida: `C:\dev\.ai\memoria`

## (raíz)
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — Arquitectura del sistema (fase 1)
- [`COST_MODEL.md`](../COST_MODEL.md) — Modelo de costos de ejecución de `ibtrader`
- [`DATA_SOURCES.md`](../DATA_SOURCES.md) — Fuentes de datos (qué provee IBKR y qué requiere externos)
- [`DECISION_ENGINE.md`](../DECISION_ENGINE.md) — Motor de decisiones (fase 1)
- [`README.md`](../README.md) — IBKR Investment System (institucional, fase 1)
- [`RISK_MODEL.md`](../RISK_MODEL.md) — Modelo de riesgo (fase 1)
- [`ROADMAP.md`](../ROADMAP.md) — Roadmap por fases (extracto)

## docs
- [`docs/PAPER-OPS.md`](../docs/PAPER-OPS.md) — Paper ops — Fase 3 (triage)

## docs/research
- [`docs/research/INSTITUTIONAL_SYSTEMATIC_STACK.md`](../docs/research/INSTITUTIONAL_SYSTEMATIC_STACK.md) — Institutional systematic stack — research synthesis (V3)
- [`docs/research/MEJORAS-EVIDENCIA-2026-11-08.md`](../docs/research/MEJORAS-EVIDENCIA-2026-11-08.md) — Mejoras con evidencia (2026-11-08)
- [`docs/research/MEJORA-ALGORITMO-2026-11-21.md`](../docs/research/MEJORA-ALGORITMO-2026-11-21.md) — Mejora del algoritmo: prueba pareada, núcleo 60/40 + tendencia y estado del paper
- [`docs/research/AUDITORIA-ALGORITMO-2026-11-22.md`](../docs/research/AUDITORIA-ALGORITMO-2026-11-22.md) — Auditoría: sin fuga de datos, robusto a retraso y costes; corregido el rechazo entero de compras sobre el 40 %
- [`docs/MODOS-DE-FALLO.md`](../docs/MODOS-DE-FALLO.md) — Cada fallo posible, qué hace el sistema y la prueba que lo demuestra
- [`docs/research/FASE-3B-CARRY-2026-11-22.md`](../docs/research/FASE-3B-CARRY-2026-11-22.md) — Fase 3: el carry con ETF no predice (IC negativo) y no entra a paper
- [`docs/research/BRECHAS-SISTEMA-2026-11-22.md`](../docs/research/BRECHAS-SISTEMA-2026-11-22.md) — Qué le falta al sistema de punta a punta, por impacto; el vigía que recupera corridas perdidas
- [`docs/research/FASE-3-MOMENTUM-RELATIVO-2026-11-21.md`](../docs/research/FASE-3-MOMENTUM-RELATIVO-2026-11-21.md) — Fase 3: el momentum relativo predice (IC 0,07–0,10) pero no pasa la prueba pareada; no entra a paper
- [`docs/research/FASES-1-2-RESULTADOS-2026-11-21.md`](../docs/research/FASES-1-2-RESULTADOS-2026-11-21.md) — Fases 1 y 2: con 2008 dentro la mezcla ya no es concluyente; el universo de 26 ETF no mejora
- [`docs/research/PLAN-MAESTRO-2026-11-21.md`](../docs/research/PLAN-MAESTRO-2026-11-21.md) — Plan maestro por fases: más apuestas independientes, no más complejidad
- [`docs/research/PROTOCOLO-INVESTIGACION.md`](../docs/research/PROTOCOLO-INVESTIGACION.md) — Protocolo de investigación de `ibtrader` (fase 1 del playbook)
- [`docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md`](../docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md) — Cómo generan sus algoritmos los fondos cuantitativos gigantes, y qué de eso cabe en ibtrad

## docs/research/quant-funds-2026-10-21
- [`docs/research/quant-funds-2026-10-21/04-ejecucion-costos-ibkr.md`](../docs/research/quant-funds-2026-10-21/04-ejecucion-costos-ibkr.md) — Anexo 4 — Ejecución, costos de transacción e Interactive Brokers

## docs/specs
- [`docs/specs/SPEC-v3-research-alpha.md`](../docs/specs/SPEC-v3-research-alpha.md) — V3 — RESEARCH / ALPHA LABORATORY (owner-authorized)

## .ai
- [`.ai/EXEC-PACKET.md`](../.ai/EXEC-PACKET.md) — EXEC-PACKET — Oleada F3++

