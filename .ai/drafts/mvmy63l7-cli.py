@app.command("run-with-risk")
def run_with_risk(
    symbol: Optional[str] = None,
    exp_id: Optional[str] = None,
    risk_on_threshold: Optional[float] = None,
) -> None:
    """
    P8 Risk Integration: regime veto + volatility-target sizing. No live orders; prints decision.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    
    # Historical regime probabilities (expanding, min window)
    bench = s.universe.benchmark if s.universe.benchmark in data else sym
    bench_close = data[bench]["close"].astype(float)
    feats_all = build_regime_features(bench_close)
    min_train = 60
    
    probs = []
    idxs = list(feats_all.index)
    for i in range(len(idxs)):
        tr_idx = idxs[: i + 1]
        if len(tr_idx) < min_train:
            probs.append(0.0)
            continue
        model, _ = fit_gmm_regime(bench_close.reindex(tr_idx), n_components=2, train_slice=slice(None))
        p = model.predict_proba(feats_all.iloc[[i]])
        # Asegurar que el modelo tenga predict_proba si no es GMM (fallback a probas uniformes o 0)
        if hasattr(model, "predict_proba"):
            probs.append(float(p[0, model.risk_on_label]))
        else:
            # Fallback básico si fit_gmm devuelve otro objeto
            # Asumiendo que en un entorno real esto es GMM, pero por seguridad:
            probs.append(0.5) 
            
    risk_on_series = _pd.Series(probs, index=feats_all.index)
    
    # Strategy with risk veto + vol-target sizing backtest
    strat = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=True,
    )

    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
    
    try:
        res = _bt(
            data=data,
            strategy=strat,
            commission_cfg=s.commission,
            slippage_cfg=s.slippage,
            direction=s.trading.direction,
            risk_on=risk_on_series,
            risk_on_threshold=thr,
            target_vol_annual=float(s.risk.target_vol_annual),
            risk_manager=RiskManager(s.risk, RiskParameters(target_vol=float(s.risk.target_vol_annual), killswitch_path=s.risk.killswitch_file)),
        )
        
        # Formatear salida JSON limpia
        import json as _json
        import pandas as pd
        
        # Extraer métricas clave del backtest (ajustando al formato de la app)
        out = {
            "exp_id": exp_id or str(pd.Timestamp.now()).replace(":", "-"),
            "symbol": sym,
            "orders_sent": len(res.get("trades", [])), # Asumiendo que 'res' tiene trades
            "returns": res.get("returns").to_dict() if hasattr(res, "get") else {},
            "terminal_value": float(res.get("terminal_value", 100000)) if isinstance(res, dict) else None,
            "sharpe_ratio": float(res.get("sharpe_ratio", 0.0)),
            "max_drawdown": float(res.get("max_drawdown", 0.0)),
        }
        
        # Si el backtest devuelve un DataFrame o Objeto complejo, simplificamos solo las métricas numéricas
        if hasattr(res, "to_dict"):
            full_out = res.to_dict()
            out["terminal_value"] = full_out.get("terminal_value")
            out["sharpe_ratio"] = full_out.get("sharpe_ratio")
            out["max_drawdown"] = full_out.get("max_drawdown")
            
        typer.echo(_json.dumps(_noneify(out), ensure_ascii=False, separators=(",", ":")))
    except Exception as e:
        # Manejo de errores básico para no romper la CLI
        typer.echo(f"Error en run-with-risk: {e}", err=True)
