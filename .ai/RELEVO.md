# RELEVO

## Hecho (2026-10-24, cursor — brief urgency)
- `deterministic_brief`: si `extra` tiene `urgency_mode` → bullet `Urgency paper: {mode} ({reason}).`; si `config_hash_ok is False` → `Config freeze: HASH MISMATCH — do not retune.`
- `tests/test_ai_brief_autopilot.py`: extra + assert urgency line if present.
- Ruff + pytest verdes. NO commit. No toqué autopilot/simulated/cli.

## Hecho (previo)
- ibc-checklist / freeze+urgency autopilot / schedule scripts.

## A medias
- Tiingo + hold-out + pia (Adam).
- Dirty local: brief.py + test_ai_brief_autopilot.py (sin commit).

## Siguiente
- Paper vivo congelado sin retocar params.
- Cuando haya Tiingo: OOS hold-out una vez.

## No tocar
- Solo main. PASS ≠ deploy. Autopilot/reconcile sin órdenes LIVE.
