# RELEVO

## Hecho (2026-10-24, cursor — W11d)
- `scripts/schedule-ibc-check.ps1`: Register|Status|Unregister|RunOnce, task `ibtrader-ibc-check`, default 08:00, runs `ibc-checklist`. Status smoke OK.
- README: 2 líneas bajo schedule para Register ibc-check.
- `src/ibtrader/ops/slippage_report.py` + CLI `slippage-report` (JSON, 0 órdenes).
- `tests/test_slippage_report_cli.py` + pytest verdes. NO commit/push pedido.
- No toqué simulated/autopilot/paper_curve/stack/brief.

## A medias
- Tiingo + hold-out + pia (Adam).

## Siguiente
- Paper vivo congelado sin retocar params.
- Cuando haya Tiingo: OOS hold-out una vez.

## No tocar
- Solo main. PASS ≠ deploy. Autopilot/reconcile/ibc-check sin órdenes LIVE.
