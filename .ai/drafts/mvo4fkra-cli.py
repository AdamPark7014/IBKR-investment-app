            n_components=2, 
        ) # Regresión a la media simple (Simple Mean Reversion):
        
        mean_ret = 0.1 # 10% return anualizado esperado (ajustable por ticker/rango)
        z_score_threshold = -mean_ret / (probs[-1] * 0.5 + 1e-9) # Umbral de salida basado en probabilidad de régimen
        
        # Condición de salida: Si la probabilidad del "buen" régimen es baja (o alta riesgo)
        current_regime_risk = 1 - probs[-1] if len(probs) > 0 else 0.5
        
        decision_info = {
            "signal": "HOLD" # Default
        }
        
        # Aplicar lógica de regresión a la media: Si el precio está por debajo del umbral de z-score ajustado
        if bench_close.iloc[-1] < (bench_close.mean() - 2.0 * bench_close.std()): 
            decision_info["signal"] = "LONG" # Entrada en zona de baja (mean reversion mean)
            decision_info["size_weight"] = 0.8 # Full size para contrarrestar tendencia
            
        elif current_regime_risk > 0.7: # Salir si la probabilidad de crisis/regimen malo es alta
            decision_info["signal"] = "FLAT" # Salida del mercado (Stop Loss/Vol Target)
            decision_info["size_weight"] = 0.0
        
        out["decision"] = decision_info
        out["regime_probs"] = probs[-1:]
        
    typer.echo(_json.dumps(_noneify(out), ensure_ascii=False, separators=(",", ":")))