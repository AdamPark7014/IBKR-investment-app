# RELEVO

## Hecho (2026-10-25, cursor — W15b)
- `src/ibtrader/ops/cli.py`: APPEND-ONLY `paper-equity` (~30 líneas) — `--path` default `data/paper_equity.jsonl`, `--append` float opcional; JSON `{n_points, max_dd, last_equity, orders_sent:0}` vía `paper_curve` (`load_equity_points`, `paper_max_drawdown`, `append_equity_point`). cli size 63468 (>50k).
- `tests/test_paper_equity_cli.py`: tmp_path empty + append 100/80/90 → max_dd 0.2
- pytest `tests/test_paper_equity_cli.py` → 1 passed
- Sin commit/push. No toqué simulated/autopilot/simple_ui/schedule.

## A medias — W15
- W15a `schedule-register-all.ps1`
- W15c `docs/PAPER-OPS.md` + README config-freeze
- W15d `open_orders` helper + touchable en autopilot

## Adam (bloquea edge, no más código)
- Tiingo API · hold-out una vez · `pia_…` opcional
- `Register` Task Scheduler (o `schedule-register-all`)
- Meses de paper congelado sin retocar params

## No tocar
- Solo main. Cero LIVE. No reescribir `cli.py` entero con Ollama.
