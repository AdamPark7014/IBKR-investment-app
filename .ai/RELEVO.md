# RELEVO

## Hecho
- Olas A–C del EXEC-PACKET cerradas en el working tree (sin commit aún).
- Fail-closed backtest; paper↔`approve_order`; gates strict + BH required; smoke CLI; broker `allow_broker_orders` + LIVE account pin; killswitch fail-closed; STOP/EMERGENCY no abren.
- Pytest focal hardening: **53 passed**.

## A medias
- B3 parcial: helpers `restricted_bar_frac` listos; engine aún no publica lockout bars.
- Ola D (shadow, hashes registry, data fail-loud) no empezada.
- `main` ahead 1 (rescate paper) + diff hardening sin commit.

## Siguiente
- Si Adam pide: commit hardening + `git pull --rebase` + push main.
- Ola D / emitir `restricted_bar_frac` desde backtest.

## No tocar
- Solo `main`. Paper-run no envía órdenes (`allow_broker_orders=False` por defecto).
- PASS de gates ≠ deploy.
