# RELEVO

## Hecho (2026-10-24, cursor — Fase 2 CLI)
- Cableado `ibtrader research-portfolio` → `run_portfolio_research` (smoke/full, universe JSON, hold-out `--confirmation`).
- Fix KeyError de benchmark en `signal-validate` si el símbolo no está en `data`.
- `test_research_portfolio_cli_smoke` en verde (~55s). Packet Fase 2 marcado [x].

## Hecho (previo)
- Ola D shadow / restricted_bar_frac / hashes; playbook fase 1; pipeline stages + HRP/boxes + portfolio_runner en main.

## A medias
- `broker/simulated.py` comisiones legadas; runners research sin `avg_cost_bps_per_order` por fila.
- Shadow `held={}` en paper-run (sin posiciones broker).
- Primera descarga Tiingo real + hold-out de confirmación: esperan inputs de Adam (token, DD, capital).

## Siguiente
- Push `main` si Adam lo pide (`ahead` local).
- Paper 2–3 meses solo si algún candidate PASS en datos reales + confirmation hold-out.
- Opcional: acortar warm-ups en smoke SystemConfig para CI más rápida.

## No tocar
- Solo `main`. PASS ≠ deploy. Hold-out una sola vez. Paper-run no envía órdenes.
