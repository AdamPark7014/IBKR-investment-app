### P9 — Resultados OOS (walk-forward, honestos)

Configuración y ventana:
- OOS: 2025-09-24 a 2026-09-23 (según ejecución en la PC del propietario)
- Universo: SPY (benchmark SPY)
- Costes incluidos (comisiones IBKR y slippage)
- Entradas a apertura t+1 (v1.1), sin fuga de información

Resultados con el motor actual (v1.1, next‑open, multi‑fold WFO):
- Los números OOS deben ser generados con:
  - `ibtrader download-data`
  - `ibtrader walk-forward --exp-id p9_wf`
- Este archivo se actualizará con los resultados por fold (fechas, parámetros elegidos, combos probados y métricas) y el agregado OOS vs B&H, todos fechados. (Pendiente de la corrida oficial en la PC del propietario.)

Números v1.0 (mismo-bar) — superados:
- SMA 10/30 (long+short): OOS CAGR -12.4%, Sharpe -1.02
- Long only: OOS CAGR +0.19%, Sharpe 0.41
- B&H: OOS CAGR +16.2%, Sharpe 1.22
Estos provienen del motor v1.0 con ejecución “mismo bar”; se mantienen aquí sólo como referencia histórica y no deben usarse para evaluar v1.1.

Conclusión honesta (a la fecha):
- Con la evidencia disponible, no hay edge OOS robusto frente a B&H. La respuesta a §49 permanece: NO — INSUFFICIENT EVIDENCE.

Resultados OOS históricos (v1.1, reportados en la R6 desde commit 4c4acb9; stitched 2024‑09‑23..2026‑09‑23; PENDIENTE de re-ejecutar en este head):
- Long only: CAGR 5.9%, Sharpe 0.74
- Long+Short: CAGR 7.7%, Sharpe 0.93
- Buy & Hold SPY: CAGR 16.2%, Sharpe 0.99

Estos números serán verificados y regenerados con `ibtrader walk-forward --exp-id p9_wf` sobre la máquina del propietario.
