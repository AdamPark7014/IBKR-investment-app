# RELEVO

## Hecho (2026-10-24, cursor — a medias costos)
- `broker/simulated.py` usa `execution.costs.total_order_cost` (+ `RegFeesConfig`); tests BUY/SELL con reg fees.
- Walk-forward `_stats_to_dict` expone `avg_cost_bps_per_order`, `total_costs`, `cost_drag_annual_pct`, `total_reg_fees` → filas OOS de research.
- Smoke `SystemConfig` en `portfolio_runner`: warm-ups cortos (scalar/fdm/idm 60, step 5).
- `paper-run --shadow` lee `data/paper_positions.json` si existe (si no, held={}).

## Hecho (previo)
- Fase 2 CLI `research-portfolio`; Ola D; playbook fase 1; pipeline stages.

## A medias
- Agentes en paralelo pueden seguir tocando costos/smoke — revisar si hay diff extra al integrar.
- Tiingo real + hold-out confirmación: inputs de Adam.
- Push `main` pendiente (`ahead` local).

## Siguiente
- Push si Adam lo pide.
- Confirmación OOS con datos reales cuando haya token Tiingo.

## No tocar
- Solo `main`. PASS ≠ deploy. Hold-out una vez. Paper-run no envía órdenes.
