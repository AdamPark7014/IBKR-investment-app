# RELEVO

## Hecho (2026-10-25)
- W11–W16 en main: paper triage + `paper-status` + `load_assumed_sharpe`.
- **W17 (este turno, sin push):**
  - `paper_status.build_paper_status` → `schedules` dict (3 schtasks, bool|None)
  - `tests/test_paper_status.py` asserts `schedules`
  - `scripts/bootstrap-paper.ps1` (open-orders sample + freeze --write + paper-status; NO Register)
  - `docs/PAPER-OPS.md` +2 líneas bootstrap
  - pytest `test_paper_status` + `test_assumed_sharpe` OK (10 passed)

## Adam (ops, no más features)
1. `pwsh -File scripts/bootstrap-paper.ps1` (triage; no schtasks)
2. `pwsh -File scripts/schedule-register-all.ps1 -Action Register` (Adam)
3. Tiingo + hold-out (+ pia)
4. Meses paper congelado — ver `docs/PAPER-OPS.md`

## Siguiente
- Commit W17 en main cuando Adam pida. PASS ≠ deploy. Cero LIVE.

## No tocar
- Solo main. No reescribir `cli.py` entero con Ollama.
