    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
    
    # Configurar límites de pérdida y ganancias si no se especifican
    stop_loss_pct = float(s.risk.params.get("stop_loss_pct", 0.10))
    take_profit_pct = float(s.risk.params.get("take_profit_pct", 0.25))

    try:
        # Ejecutar backtest con riesgo integrado (veto de régimen + tamaño objetivo)
        bt_result = _bt(
            strat=strat,
            data=data,
            symbol=sym,
            risk_model=risk_on_series,
            threshold=thr,
            stop_loss=stop_loss_pct,
            take_profit=take_profit_pct,
            cash_initial=float(s.risk.params.get("initial_capital", 100_000)),
        )

        # Extraer métricas clave del backtest
        equity_curve = bt_result["equity"]
        trades = bt_result.get("trades", [])
        
        cagr = float(bt_result.get("cagr", 0.0))
        sharpe = float(bt_result.get("sharpe_ratio", 0.0))
        max_dd = float(bt_result.get("max_drawdown", 0.0))
        num_trades = len(trades)
        
        # Construir resumen de órdenes (simuladas, ya que es un entorno de paper/risk)
        orders_summary = []
        for t in trades[:10]: # Limitar a las primeras 10 para el reporte JSON
            order_info = {
                "entry_date": str(t.get("entry_date")),
                "exit_date": str(t.get("exit_date")),
                "direction": str(t.get("direction", "long") if "direction" in t else "neutral"),
                "profit_pct": float(t.get("profit_pct", 0.0)),
                "exit_reason": str(t.get("reason", "signal"))
            }
            orders_summary.append(order_info)

        # Resumen de régimen (última predicción si es posible, o promedio reciente)
        # Usamos el último valor calculado para contexto
        latest_regime_prob = risk_on_series.iloc[-1] if len(risk_on_series) > 0 else 0.5
        
        result_report = {
            "status": "success",
            "symbol": sym,
            "risk_on_threshold": thr,
            "current_regime_prob": float(latest_regime_prob),
            "regime_veto_active": latest_regime_prob >= thr,
            "metrics": {
                "cagr": cagr,
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "num_trades": num_trades,
                "win_rate": float(bt_result.get("win_rate", 0.0)),
            },
            "summary_orders": orders_summary,
            "equity_final": float(equity_curve.iloc[-1]) if len(equity_curve) > 0 else 0.0,
            "equity_start": float(equity_curve.iloc[0]) if len(equity_curve) > 0 else 0.0
        }

        typer.echo(_json.dumps(_noneify(result_report), ensure_ascii=False, separators=(",", ":")))

    except Exception as e:
        error_msg = {
            "status": "error",
            "message": str(e),
            "symbol": sym,
        }
        typer.echo(_json.dumps(_noneify(error_msg), ensure_ascii=False, separators=(",", ":"))))