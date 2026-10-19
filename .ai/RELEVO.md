# RELEVO

## Hecho
- Motor de papel: `paper-run` ya no fuerza `NO_TRADE`. Clasifica BUY/SELL/WATCH/NO_TRADE con filtro de régimen, tamaño por volatilidad, tope de exposición y vetos (kill switch, símbolo, datos, stop ATR). No envía órdenes.
- Tests de política y del motor en verde (ruff + mypy en los archivos tocados).

## A medias
- Suite completa: `tests/test_research_cli.py::test_research_run_cli_full_suite` no terminó en varios minutos (ya era lenta; no la toqué).

## Siguiente
- Si Adam quiere el siguiente salto: meta-labeling TAKE/SKIP encima de esta política, o champion/challenger en sombra. Sigue sin órdenes LIVE.

## No tocar
- No abrir largos sin régimen risk-on (sin VIX el filtro apaga scores positivos).
- No conectar este motor al broker. LIVE sigue bloqueado por `live_safety_ok`.
