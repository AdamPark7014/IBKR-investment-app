# RELEVO

## Hecho (2026-10-24, cursor — tsmom/MR costos + CI)
- tsmom + mean_reversion runners: `reg_fees` + `avg_cost_bps_per_order` / `cost_drag` en OOS stitched.
- CI clean-install: `research-portfolio --profile smoke`.
- `uv.lock` fuera del índice + en `.gitignore` (pip sigue siendo el camino oficial).

## Hecho (previo)
- Sim IBKR, WF costos, smoke warmups, shadow held JSON, Fase 2 CLI.

## A medias
- Tiingo real + hold-out: inputs de Adam (token, DD, capital).

## Siguiente
- Tras push: vigilar CI ubuntu/macOS (portfolio smoke ~1 min extra).
- Confirmación OOS cuando haya Tiingo.

## No tocar
- Solo `main`. PASS ≠ deploy. Hold-out una vez. Paper-run sin órdenes.
