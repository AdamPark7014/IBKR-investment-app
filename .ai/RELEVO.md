# RELEVO

## Hecho (2026-10-24, cursor — W11a paper max DD)
- NEW `src/ibtrader/ops/paper_curve.py`: load_equity_points / max_drawdown / paper_max_drawdown.
- NEW `tests/test_paper_curve.py`: empty, rising, 100→80→90 DD=0.2.
- `autopilot.py`: evaluate_paper_alerts max_drawdown from paper_equity.jsonl if exists else None.
- pytest test_paper_curve + test_ai_brief_autopilot OK. NO commit. No toqué cli/simulated/stack/schedule.

## Hecho (previo)
- brief urgency; ibc-checklist / freeze+urgency / schedule scripts.

## A medias
- Tiingo + hold-out + pia (Adam).

## Siguiente
- Paper vivo congelado sin retocar params.
- Cuando haya Tiingo: OOS hold-out una vez.

## No tocar
- Solo main. PASS ≠ deploy. Autopilot/reconcile sin órdenes LIVE.
