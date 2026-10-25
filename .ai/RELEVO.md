# RELEVO

## Hecho (2026-10-25)
- W11–W16 en `origin/main`: paper triage code cerrado + `paper-status` + `load_assumed_sharpe`.
- Tip esperado tras push: `c4e5b85`.

## Adam (ops, no más features)
1. `pwsh -File scripts/schedule-register-all.ps1 -Action Register`
2. `ibtrader config-freeze --write` (opcional `assumed_sharpe` en el JSON)
3. Tiingo + hold-out (+ pia)
4. Meses paper congelado — ver `docs/PAPER-OPS.md`

## Siguiente
- Solo código si Adam pide un hueco concreto. PASS ≠ deploy. Cero LIVE.

## No tocar
- Solo main. No reescribir `cli.py` entero con Ollama.
