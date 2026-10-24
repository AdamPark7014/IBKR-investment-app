    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
    
    # Asegurar que tenemos un índice para el backtest
    if not isinstance(feats_all, _pd.DataFrame):
        feats_all = _pd.DataFrame([feats_all]).T
        
    # Ejecutar backtesting con control de riesgo integrado
    try:
        results = _bt(
            data, 
            strat, 
            init_cash=100_000.0,
            commission=0.001, 
            slippage_pct=0.0005, 
            risk_mode="vol_target" # Usamos vol-target para normalizar posición según volatilidad
        )
    except Exception as e:
        rprint({"error": str(e)})
        typer.echo(_json.dumps({"error": "Backtest execution failed", "details": str(e)}, indent=2))
        return

    if "positions" in results and isinstance(results["positions"], _pd.DataFrame):
        # Filtrar posiciones para el último activo (o primer si es único)
        try:
            last_pos = results["positions"].iloc[-1:]
            # Calcular exposición final normalizada a riesgo (volatilidad objetivo)
            # Asumiendo que 'position_size' o 'value' está en las columnas.
            # Si no, asumimos que el motor devolvió el valor de la posición.
            
            # Extraer métricas de backtest si están disponibles
            bt_stats = {}
            if "stats" in results:
                bt_stats = {k: float(v) for k, v in results["stats"].items() if isinstance(v, (int, float))}
            
            # Obtener última probabilidad de riesgo en activo para incluir en el reporte
            last_prob = risk_on_series.iloc[-1]
            
            # Determinar si se activó la "muerte" (Stop Risk)
            kill_event = "Kill" if bt_stats.get("kill_reason") else None
            
            report = {
                "exp_id": exp_id or results.get("run_id", ""),
                "symbol": sym,
                "strategy": str(type(strat)),
                "risk_threshold": thr,
                "last_risk_prob": round(last_prob, 4),
                "risk_active": last_prob >= thr if "Kill" not in str(kill_event) else True,
                "positions": {
                    k: float(v["position_size"] if isinstance(v, _pd.Series) and "position_size" in v.index 
                              else v.iloc[0]) 
                    for k, v in last_pos.items() 
                } if not kill_event else {"status": "KILLED"},
                **bt_stats
            }
        except Exception as e2:
            rprint({"error": "Failed to extract backtest results", "details": str(e2)})
            report = {
                "exp_id": exp_id or "",
                "symbol": sym,
                "status": "ERROR",
                "details": str(e2)
            }
    else:
        # Fallback si el formato de resultados es diferente (ej. dict simple)
        stats = results if isinstance(results, dict) else {}
        report = {
            "exp_id": exp_id or "",
            "symbol": sym,
            "risk_threshold": thr,
            "last_risk_prob": round(last_prob, 4) if "risk_on_series" in dir() else None,
            **{k: float(v) for k, v in stats.items() if isinstance(v, (int, float))}
        }

    typer.echo(_json.dumps(_noneify(report), ensure_ascii=False, separators=(",", ":")))


# Resto del archivo original sigue aquí...