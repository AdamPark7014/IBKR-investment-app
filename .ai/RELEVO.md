# RELEVO

## Hecho (2026-10-25 noche)
- Sim campaign SPY ~1253 barras (Yahoo):
  - backtest-sample, walk-forward 3 folds, run-with-risk, research-run smoke
  - Resumen diario: `reports/sim_daily_pnl_summary.json`
  - Scripts: `scripts/analyze_wf_daily_pnl.py`
- Scheduler ya registrado (turno anterior).

## Hallazgo P&L (honesto)
- Full-sample SMA: CAGR ~4.1% Sharpe ~0.73 vs BH CAGR ~12.4%
- Walk-forward OOS cosido: CAGR ~3.4% Sharpe ~0.49 **expectancy −$1886**/trade
- Fold1 (2024-10→2025-06): **−$1.2k** en ~166 días
- Fold2 (2025-06→2026-02): **+$5.9k**
- Fold3 (2026-02→2026-10): **+$2.7k**
- Costos del modelo (~0.55 bp) **demasiado baratos** vs piso IBKR 2.5 bp → P&L optimista
- **No retocar** params SMA con este OOS (playbook)

## Adam
1. Tiingo + hold-out una vez
2. Subir realismo de costes antes de “mejorar alfa”
3. Meses paper congelado

## No tocar
- Solo main. Cero LIVE. No curve-fit al último fold.
