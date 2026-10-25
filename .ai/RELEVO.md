# RELEVO

## Hecho
- W11–W15 en `origin/main`.
- **W16b** (este turno): `load_assumed_sharpe(freeze_path, default=0.8)` en `config_freeze.py` (top-level o `snapshot.assumed_sharpe`, sin tocar hash schema); autopilot usa ese valor en `compare_paper_vs_oos` + `evaluate_paper_alerts`; `tests/test_assumed_sharpe.py`. `pytest -q` verde. Sin push. Sin tocar `cli.py`.

## A medias — W16
- W16a `paper-status` CLI (si sigue pendiente en otro agente)

## Adam (ya no es código)
1. `pwsh -File scripts/schedule-register-all.ps1 -Action Register`
2. Opcional en freeze JSON: `"assumed_sharpe": 0.8` (top-level, fuera del snapshot hasheado)
3. Tiingo + hold-out + pia opcional
4. Meses paper sin retocar

## No tocar
- Solo main. Cero LIVE. No reescribir `cli.py` entero.
