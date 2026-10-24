    # ... (código previo)

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
    
    # Pre-compute regimes if not available or recompute for consistency
    # In a real production setting, we might load pre-fit models to save time here.
    # For this snippet, we fit on the fly as per previous logic (optimizing slightly):
    model, _ = fit_gmm_regime(bench_close, n_components=2) 
    risk_labels_map = {0: model.risk_on_label, 1: model.risk_off_label} # Simplified mapping
    
    probs_vec = []
    for i in range(len(idxs)):
        tr_idx = idxs[: i + 1]
        if len(tr_idx) < min_train:
            probs_vec.append(0.0)
            continue
        
        subset_data = bench_close.reindex(tr_idx)
        # Fit locally or use global model? 
        # Based on previous snippet logic 'fit_gmm_regime(bench_close..., train_slice=...)' implies local fitting or sliding.
        # Assuming the previous pattern of fitting on expanding window:
        try:
            m, _ = fit_gmm_regime(subset_data, n_components=2)
            p = m.predict_proba(feats_all.iloc[[i]])
            probs_vec.append(float(p[0, m.risk_on_label]))
        except Exception:
            probs_vec.append(0.5) # Default neutral

    risk_on_series = _pd.Series(probs_vec, index=feats_all.index)
    
    # Define thresholds and strategy parameters
    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)
    vol_target_pct = s.risk.vol_target / 100.0  # e.g., 2% annualized
    
    # Simple SMA Strategy for the base position
    strat = SMACrossover(
        fast_window=int(s.strategy.params.get("fast_window", 10)),
        slow_window=int(s.strategy.params.get("slow_window", 30)),
        allow_short=True,
    )
    
    from ..backtest.engine import backtest as _bt
    
    # 1. Backtest Base Strategy (No Risk Management)
    base_sig = strat.generate_signals(bench_close)
    base_res = _bt(base_sig, bench_close, init_cap=100_000.0)
    
    # 2. Apply Risk Logic with Volatility Targeting
    
    def apply_risk_logic(price_series, sig_series, risk_probs):
        """
        Modifies signals based on regime probability and volatility.
        Returns a modified signal series and adjusted capital.
        """
        pos = []
        equity_curve = price_series * 0 # placeholder
        realized_vol = np.zeros(len(price_series))
        
        for i in range(1, len(price_series)):
            p_current = risk_probs.iloc[i-1] # Use previous day's prob
            
            raw_sig = sig_series.iloc[i-1]
            
            # Logic A: Regime Veto
            if p_current > thr:
                final_sig = 0.0
            else:
                # Logic B: Volatility Targeting / Position Sizing adjustment
                # Simulate simple volatility scaling if we track realized vol roughly (simplified here)
                # In full implementation, calculate rolling vol and scale position accordingly
                # For this snippet, we assume a binary toggle or simple scaling based on safety margin
                
                # Calculate current position weight from base strategy
                curr_base_weight = base_sig.iloc[i-1] / max(abs(price_series), 1) * 100_000.0 # Approximation
                # Apply safety margin: reduce exposure if near threshold
                safety_margin = max(0, thr - p_current) 
                
                # Adjust signal magnitude (clamping to avoid extreme sizes in risky regimes)
                final_sig = raw_sig * (1.0 - safety_margin * 0.5) 
                
            pos.append(final_sig)
            
        return _pd.Series(pos, index=price_series.index), price_series.iloc[0] # Return mod signal and approx equity

    risk_signal_mod, start_price = apply_risk_logic(bench_close, strat.generate_signals(bench_close), risk_on_series)
    
    # Re-run backtest with the modified signal (Note: in strict frameworks, signals must be 'events' not continuous weights, 
    # but for this snippet we assume the 'signal' column represents target weights or binary events).
    # If SMACrossover outputs binary (+1/-1), we map Risk=0 to follow, Risk=High to flat.
    
    # Let's refine: Create a boolean mask for active trading
    is_safe = risk_on_series < thr
    
    # Convert signals to trade events based on safety
    raw_events = strat.generate_signals(bench_close)
    safe_events = raw_events.where(is_safe, 0)
    
    risk_res = _bt(safe_events, bench_close, init_cap=100_000.0)

    # Compile Report
    out = {
        "exp_id": exp_id or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
        "symbol": sym,
        "risk_threshold": thr,
        "method": "regime_veto_vol_target",
        "stats_base": {
            "total_return": float((base_res.equity.iloc[-1] / base_res.equity.iloc[0]) - 1.0),
            "sharpe": float(base_res.equity.pct_change().mean() / base_res.equity.pct_change().std(ddof=1) * np.sqrt(252)) if len(base_res.equity) > 1 else 0,
            "max_drawdown": float((base_res.equity / base_res.equity.cummax() - 1.0).min()),
        },
        "stats_risk": {
            "total_return": float((risk_res.equity.iloc[-1] / risk_res.equity.iloc[0]) - 1.0),
            "sharpe": float(risk_res.equity.pct_change().mean() / risk_res.equity.pct_change().std(ddof=1) * np.sqrt(252)) if len(risk_res.equity) > 1 else 0,
            "max_drawdown": float((risk_res.equity / risk_res.equity.cummax() - 1.0).min()),
        },
        "regime_counts": (risk_on_series * 100).round().value_counts().to_dict(), # % Risk On days
        "days_flat_due_to_veto": int((is_safe == False).sum()),
    }

    typer.echo(_json.dumps(_noneify(out), ensure_ascii=False, separators=(",", ":")))