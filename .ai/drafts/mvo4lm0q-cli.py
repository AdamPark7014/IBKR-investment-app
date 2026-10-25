    model, rep = fit_gmm_regime(data[bench]["close"].astype(float), n_components=2)
    
    # Calcular ventana deslizante para obtener probabilidades históricas
    min_train = 60
    probs = []
    idxs = list(bench_close.index)
    model_loaded, _ = fit_gmm_regime(bench_close.iloc[-min_train:].astype(float), n_components=2) # Inicializar o usar modelo pre-entrenado si hubiera (aquí simplificado a re-fit o fit incremental conceptual)

    # Para ser consistentes con el bloque anterior proporcionado en tu prompt, asumimos que el bucle estaba intentando hacer un "rolling window" 
    # pero para simplificar la implementación funcional aquí y evitar recalcular todo en cada iteración si no es necesario,
    # recalcularemos las probabilidades sobre ventanas móviles o usaremos el modelo global sobre el histórico completo.
    # Dado que `fit_gmm_regime` parece entrenar desde cero cada vez (o sobre un slice), haremos una aproximación estándar:
    
    import numpy as np

    # 1. Preparar características/retornos para la ventana móvil si se requiere, o usar el modelo sobre todo el periodo útil
    # En muchos casos de riesgo, se usa el régimen actual estimado basado en los últimos N periodos vs un límite temporal.
    
    # Calculamos las probabilidades de régimen para cada punto histórico (ventana móvil)
    regime_probs_hist = []
    
    if len(bench_close) >= min_train:
        # Usar una ventana fija del tamaño mínimo de entrenamiento para obtener la probabilidad del "régime actual" en ese momento
        # Nota: Esto es costoso computacionalmente. En producción se usa un modelo estático sobre el full history y pide las features actuales.
        # Aquí implementamos la lógica solicitada siguiendo la estructura de bucle del prompt (aunque con optimización implícita):
        
        for i in range(len(idxs) - min_train + 1):
            window = bench_close.iloc[i:i+min_train].astype(float)
            try:
                m, _ = fit_gmm_regime(window, n_components=2)
                # Obtenemos la probabilidad para el último día de esa ventana (que representa el estado "hoy" relativo al entrenamiento)
                probs = m.predict_proba(window.iloc[[-1:]]).flatten()
                regime_probs_hist.append(probs[-1])
            except Exception as e:
                # Si falla por pocos datos o error del modelo, asumimos probabilidad neutra (50/50) o 0 riesgo
                pass

    if not regime_probs_hist:
        regime_probs_hist = [0.5] * len(bench_close)

    # Convertir a DataFrame para alineación fácil si fuera necesario, o usar lista directa
    # Calculamos el umbral de riesgo actual (probabilidad de estar en un régimen adverso o volatilidad alta)
    
    # Definimos cómo determinar el estado actual (última ventana disponible)
    current_regime_prob = regime_probs_hist[-1] if regime_probs_hist else 0.5
    
    # Parámetros de riesgo (asumiendo que vienen de s.risk si existen, o valores por defecto para la demo CLI)
    risk_threshold = s.risk.params.get("risk_on_threshold", risk_on_threshold or 0.2) # Default: veto si prob_risk > 0.2
    
    is_risky = current_regime_prob > risk_threshold
    
    # Calcular volatilidad objetivo y tamaño de posición (Volatility Targeting)
    target_vol = s.risk.params.get("target_vol_ann", s.universe.benchmark_daily_vol) if hasattr(s, 'risk') and hasattr(s.risk, 'params') else 0.25
    
    # Volatilidad estimada actual (simulada o desde datos recientes)
    recent_close = bench_close.tail(60)
    if len(recent_close) > 1:
        returns = recent_close.pct_change().dropna()
        est_vol_daily = returns.std() * np.sqrt(252) # Alinear a anual
    else:
        est_vol_daily = 0.0
        
    # Target sizing factor (inverso de la volatilidad estimada relativa al objetivo)
    vol_scaling_factor = min(est_vol_daily / target_vol, 1.0) if target_vol > 0 else 1.0
    
    risk_signal = "HOLD"
    
    if is_risky:
        risk_signal = "NO_TRADE" # Kill-switch triggered
    else:
        # Determinar dirección de la señal (simplificado a long por defecto para la demo, 
        # pero en producción leerías una señal del strategy)
        signal_direction = s.strategy.params.get("default_side", "long") 
        
        risk_signal = "SIGNAL" if signal_direction == "long" else "HOLD"

    decision = {
        "symbol": sym,
        "timestamp": bench_close.index[-1],
        "regime_prob_adverse": current_regime_prob,
        "risk_on_threshold": float(risk_threshold),
        "is_risky_flag": is_risky,
        "volatility_current": float(est_vol_daily),
        "volatility_target": float(target_vol),
        "scaling_factor": float(vol_scaling_factor),
        "size_percentage": float(vol_scaling_factor * 100) if not is_risky else 0.0,
        "action": risk_signal,
        "message": f"Risk Veto: {is_risky} | Vol Targeting: {vol_scaling_factor:.2f}"
    }

    # Si se pidió un exp_id específico, guardaríamos el estado (en una app real, aquí solo imprimimos)
    
    typer.echo(_json.dumps(_noneify(decision), ensure_ascii=False, separators=(",", ":")))