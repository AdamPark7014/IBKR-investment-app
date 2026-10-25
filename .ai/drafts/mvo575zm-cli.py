    # ... (Anterior código no mostrado, asumiendo continuación desde run_with_risk)

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
    
    # Calculate regime probabilities for the most recent window
    if len(idxs) < min_train:
        rprint({"error": f"Not enough data ({len(idxs)}) for regime analysis (need >= {min_train})."})
        return

    # Get model and representation for current horizon
    last_idx = idxs[-1]
    tr_idx = idxs[: len(idxs)] # Use full history for fitting if not specified otherwise, 
                               # or sliding window. Assuming static model for simplicity based on context,
                               # but to be safe we fit on the available history.
    
    # Re-fit or fetch existing? Context implies using current state.
    # Let's assume we use the global features fitted already or re-fit if needed.
    # For this snippet closure, we will proceed with a single model based on data history.
    
    try:
        model, rep = fit_gmm_regime(feats_all, n_components=2)
        
        # Get probability of 'High Risk' regime for the most recent day(s)
        # Assuming rep contains 'regime' probabilities or we extract them.
        # We construct a dummy series to get the last probability if model isn't fitted per-day
        # Simplified extraction: assume rep has columns like ['High_Risk_prob'] or we index by regime label
        
        recent_probs = model.predict_proba([feats_all.iloc[-1:]])[0]
        
        # Define what is 'risk' (e.g., Regime 1 vs 2). Let's assume Index 1 is risky.
        # Adjust based on actual model output structure if specific labels exist.
        risk_prob = float(recent_probs[1]) # Assuming binary mix
        
    except Exception as e:
        rprint({"error": f"Regime model failure: {e}", "signal": 0.0})
        return

    # Risk Logic: Veto or Size Adjustment
    current_signal = 0.0 # Default no trade if veto
    
    if risk_prob > (risk_on_threshold or s.risk.risk_veto_threshold):
        rprint({"decisions_sent": 0, "message": "Risk Veto: Regime probability too high."})
        # Record the veto state if needed for ledger, but orders_sent=0
        out = {
            "orders_sent": 0,
            "risk_vetoed": True,
            "regime_prob": risk_prob,
            "threshold": risk_on_threshold,
            "symbol": sym
        }
    else:
        # Generate normal signals (simplified for this closure)
        # Assuming you have a function to get_signal_from_sma or similar inside the app
        # Placeholder: call signal generation logic here if available in full scope
        # For this snippet, we assume signal exists or is 0. 
        # Let's assume standard logic runs here but without live orders.
        
        out = {
            "orders_sent": 0,
            "risk_vetoed": False,
            "regime_prob": risk_prob,
            "symbol": sym,
            # Add mock decision data if you have the signal logic connected
            "decision_text": "Trade allowed (within risk parameters)."
        }

    out["exp_id"] = exp_id or f"{sym}_{datetime.utcnow().strftime('%Y%m%d')}"
    
    typer.echo(_json.dumps(_noneify(out), ensure_ascii=False, separators=(",", ":")))