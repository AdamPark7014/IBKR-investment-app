    # ... (El resto de tu importaciones y código previo)

@app.command("walk-forward")
def walk_forward(exp_id: Optional[str] = None) -> None:
    """
    P9 Walk Forward: train/validate/test by time with frozen params; OOS never used for tuning.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    wf, summary = walk_forward_sma(s, data, sym, direction=s.trading.direction)

    # Preparar el objeto de resultados para imprimir o guardar
    run_id = exp_id or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # Reconstituir la curva de valor desde los datos stitchead si están disponibles
    eq_pairs = summary.get("stitched_oos_equity") or []
    if eq_pairs:
        df_dates, df_vals = zip(*eq_pairs)
        # Aseguramos que las fechas sean objetos pd.Timestamp o convertibles
        try:
            index_dates = [_pd.to_datetime(t) for t in df_dates]
            equity_curve = _pd.Series(df_vals, index=index_dates).sort_index()
            
            if len(equity_curve) > 1:
                rets = equity_curve.pct_change().fillna(0.0)
                
                # Calcular estadísticas básicas de la curva final
                init_capital = equity_curve.iloc[0]
                final_value = equity_curve.iloc[-1]
                total_return_val = (final_value / init_capital) - 1
                
                vol_ann = equity_curve.std() * np.sqrt(252) if len(equity_curve) > 1 else 1.0 # Evitar div por cero
                
                stats_dict = {
                    "cagr": (final_value / init_capital) ** (252 / len(equity_curve)) - 1,
                    "sharpe": rets.mean() / (rets.std(ddof=0) or 1e-9) * np.sqrt(252),
                    "sortino": None, # Omitido por brevedad si no hay tasa libre de riesgo definida
                    "max_drawdown": (equity_curve / equity_curve.cummax() - 1.0).min(),
                }

                trade_count = int(summary.get("oos_total_trades", 0) or 0)
                total_commission = float(summary.get("oos_commission_approx", 0.0) or 0.0)
            else:
                # Caso de datos insuficientes para calcular
                stats_dict = {
                    "cagr": np.nan, "sharpe": np.nan, "sortino": np.nan, 
                    "max_drawdown": 0.0, "trade_count": 0, "total_commission": 0.0
                }
        except Exception:
            # Fallback si el cálculo falla (fechas inválidas)
            stats_dict = {"cagr": np.nan, "sharpe": np.nan, "max_drawdown": 0.0}
            equity_curve = None
    else:
        equity_curve = None
        stats_dict = {k: float("nan") for k in ["cagr", "sharpe"]}
        
    # Preparamos los trades para impresión si existen
    oos_trades_list = []
    folds = summary.get("folds", [])
    for fold_data in folds:
        trades_in_fold = fold_data.get("oos_trades", [])
        for tr in trades_in_fold:
            oos_trades_list.append({
                "date": str(tr.get("date")),
                "symbol": str(tr.get("symbol")),
                "qty": int(tr.get("qty")),
                "price": float(tr.get("price")),
                "reason": str(tr.get("reason", "signal"))
            })

    # Construimos un objeto simulado de resultado compatible con lo que espera la suite
    class _WalkForwardResult:
        def __init__(self, stats, equity_curve, trades):
            self.equit = equity_curve
            self.stats = stats
            self.trades = trades
            self.cagr = stats.get("cagr")
            self.sharpe = stats.get("sharpe")
            self.max_dd = stats.get("max_drawdown")

    final_result_obj = _WalkForwardResult(stats_dict, equity_curve, oos_trades_list)

    # Output para el usuario (Rprint format similar al resto del script)
    rprint(
        {
            "symbol": sym,
            "run_id": run_id,
            "walk_forward_summary": {
                "folds_analyzed": len(folds),
                "oos_equity_available": bool(equity_curve is not None and len(equity_curve) > 0),
                "final_metrics": {
                    "cagr": float(stats_dict.get("cagr")),
                    "sharpe": float(stats_dict.get("sharpe")) if stats_dict.get("sharpe") else None,
                    "max_drawdown": float(stats_dict.get("max_drawdown"))
                },
                "total_oos_trades": len(oos_trades_list),
            }
        }
    )

    # Opcional: Guardar el artefacto si fuera necesario en un entorno real
    # art_path = save_run_artifact(final_result_obj, s, data, s.data.reports_dir, f"walkforward_{run_id}")