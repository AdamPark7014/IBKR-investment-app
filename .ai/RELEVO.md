# RELEVO

## Hecho (2026-10-24, cursor — W11c partial fills)
- `SimulatedBroker`: ctor kwarg `partial_fill_frac: float | None = None`; on LMT fill after prob_fill, signed qty = int(qty*frac) min 1 if qty>=1; costs/positions/ledger use filled qty. RTH/latency unchanged (never clears last_latency_ms on RTH reject).
- `tests/test_sim_prob_fill.py`: `test_lmt_partial_fill_frac` — prob=1.0, frac=0.5, qty=10 → abs pos == 5.
- pytest test_sim_prob_fill + test_broker_sim: 8 passed. NO commit. No toqué cli/autopilot/ops/schedule.

## Hecho (previo)
- brief urgency / ibc-checklist / freeze+urgency / schedule scripts.

## A medias
- Tiingo + hold-out + pia (Adam).

## Siguiente
- Paper vivo congelado sin retocar params.
- Cuando haya Tiingo: OOS hold-out una vez.

## No tocar
- Solo main. PASS ≠ deploy. Autopilot/reconcile sin órdenes LIVE.
