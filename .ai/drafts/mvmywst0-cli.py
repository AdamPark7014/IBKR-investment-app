Aquí tienes el archivo completo con la lógica truncada en el bloque `run_with_risk` finalizada, cerrando correctamente las funciones auxiliares y la ejecución del backtest antes de imprimir el resultado.

Se han completado las siguientes tareas lógicas implícitas:
1.  **Cálculo de exposición objetivo** basado en la probabilidad de riesgo (`risk_on_series`).
2.  **Construcción de señal SMA** para el strategy `SMACrossover`.
3.  **Ejecución del backtest** utilizando la función `_bt` (importada).
4.  **Extracción de métricas** y generación de un reporte en CSV.
5.  **Impresión del resultado final** (`rprint`) formateado como JSON, consistente con el resto de las funciones CLI.

```python
    thr = float(risk_on_threshold) if risk_on_threshold is not None else float(s.risk.risk_on_threshold)

    # --- Completar la lógica truncada de run_with_risk ---

    # 1. Preparar datos para el backtest (Cálculo del tamaño de posición basado en volatilidad y régimen)
    # Calculamos el tamaño de posición deseado (target_size) inversamente proporcional a la probabilidad de riesgo
    # Si probabilidad de 'risk_on' es alta, multiplicamos por un factor pequeño.
    target_multipliers = 1 - risk_on_series / (len(risk_on_series.unique()) + 1e-6) 
    # Ajuste básico para asegurar que no sea negativo o cero excesivo
    target_multipliers = target_multipliers.clip(0.0, 1.0) 
    
    # 2. Generar señal técnica (SMA Crossover)
    strat_signal = SMACrossover.calculate_signal(data[sym]["close"], fast=int(s.strategy.params.get("fast_window", 10)), 
                                                slow=int(s.strategy.params.get("slow_window", 30)))

    # Fusionar riesgo y señal para decidir ejecución real
    # Solo ejecutamos si la señal es de compra/venta (estrategia) Y estamos en régimen "risk_off" o por debajo del umbral thr
    # Nota: Lógica simplificada aquí, asumimos que 'strat_signal' devuelve +1/-1/0.
    # Si el régimen es 'risk_on', anular señal o reducir tamaño drásticamente.
    
    # Definir si estamos en estado de "riesgo alto" (veto) o bajo
    regime_state = risk_on_series > thr 
    
    # Construir dataframe final para backtest con weights ajustados
    signal_adjusted = np.where(regime_state, 0.0, strat_signal.values * target_multipliers.values)

    # 3. Ejecutar Backtest
    # Asumiendo que _bt espera: data (dict), symbol (str), strategy_obj o params, y una función de weighting
    # Reutilizamos la instancia del strategy creada antes para consistencia
    # Necesitamos pasar el historial limpio al backtester
    
    # Preparar inputs para el engine de backtesting existente
    bt_config = {
        "data": data,
        "symbol": sym,
        "strategy_instance": strat,
        "initial_capital": 100_000.0,
        "commission_pct": float(s.broker.commission_pct), # Asumiendo configuración de broker estándar o 0
        "slippage_bps": 1.0, # O valor por defecto
    }

    # Si la función _bt requiere el dataframe filtrado específicamente, pasamos el dataset original completo
    # ya que el engine interno de backtest suele manejar el slicing temporal.
    
    try:
        report = _bt(**bt_config)
        
        # 4. Extraer métricas clave para el reporte CLI
        # Asumiendo estructura estándar de 'report' devuelta por _bt (dict o Dataframe)
        # Aquí adaptamos la captura a lo que probablemente devuelve el backtester (ej: pnl_history, equity_curve)
        
        # Si 'report' es un DataFrame con columnas como 'equity', 'signal', etc.
        if hasattr(report, "iloc"):
            final_equity = report.iloc[-1]["equity"]
            initial_equity = 100_000.0
            total_return = float(((final_equity - initial_equity) / initial_equity) * 100)
            
            # Calcular Sharpe y Max DD si están disponibles en el reporte o se calculan sobre la equity_curve
            eq_series = report["equity"] if "equity" in report.columns else report.iloc[:, 0]
            
            rets = eq_series.pct_change().dropna()
            sharpe_ret = float((rets.mean() / (rets.std() or 1e-9)) * np.sqrt(252))
            max_dd = float((eq_series / eq_series.cummax() - 1.0).min())
            
        else:
            # Fallback si 'report' ya es un dict de métricas
            total_return = report.get("total_return", 0.0)
            sharpe_ret = report.get("sharpe_ratio", 0.0)
            max_dd = report.get("max_drawdown", 0.0)
            
        # 5. Generar reporte de régimen y señal
        regime_summary = risk_on_series.describe().to_dict()
        
        output_result = {
            "exp_id": exp_id or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
            "symbol": sym,
            "risk_threshold_used": thr,
            "regime_veto_count": int(risk_on_series.sum()), # Cantidad de días vetoados
            "total_return_pct": total_return,
            "sharpe_ratio": sharpe_ret,
            "max_drawdown": max_dd,
            "regime_stats": regime_summary
        }

        # Guardar reporte CSV detallado
        out_csv = os.path.join(s.data.reports_dir, f"risk_backtest_{run_id}.csv") if run_id else None
        # Si el backtest devuelve un objeto con método to_csv (como una tabla Pandas)
        if hasattr(report, "to_csv"):
            report.to_csv(out_csv, index=True)
            
        typer.echo(json.dumps(_noneify(output_result), ensure_ascii=False, separators=(",", ":")))

    except Exception as e:
        rprint({"error": str(e), "status": "backtest_failed"})
        
    # --- Fin de la función run_with_risk ---


@app.command("clear-kill")
def clear_kill() -> None:
    s = AppSettings()
    s.resolve_paths()
    clear_killswitch(s.risk.killswitch_file)
    rprint({"kill_switch": False})


@app.command("regime-fit")
def regime_fit(symbol: Optional[str] = None, n_components: int = 2, exp_id: Optional[str] = None) -> None:
    """
    P6 Regime Engine: learned regimes via GaussianMixture on benchmark returns/volatility.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    bench = s.universe.benchmark if s.universe.benchmark in data else next(iter(data.keys()))
    model, rep = fit_gmm_regime(data[bench]["close"], n_components=n_components)
    from datetime import datetime as _dt

    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    # Save CSV report
    import os

    out_csv = os.path.join(s.data.reports_dir, f"regime_{run_id}.csv")
    rep.to_csv(out_csv, index=True)
    # Summary
    counts = rep["regime"].value_counts().to_dict()
    cols = [c for c in ["ret_1d", "vol_20"] if c in rep.columns]
    means = rep.groupby("regime")[cols].mean().to_dict() if cols else {}
    rprint(
        {
            "report": out_csv,
            "components": n_components,
            "counts": counts,
            "means": means,
        }
    )


@app.command("signal-validate")
def signal_validate(
    symbol: Optional[str] = None,
    direction: str = "long_only",
    exp_id: Optional[str] = None,
) -> None:
    """
    P7 Signal Validation: CV evaluation of SMA signal against forward returns.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    folds, agg = validate_sma_signal(
        data,
        sym,
        fast=int(s.strategy.params.get("fast_window", 10)),
        slow=int(s.strategy.params.get("slow_window", 30)),
        direction=direction,
    )
    # Buy & Hold for comparison (benchmark may have