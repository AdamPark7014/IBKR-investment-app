Aquí tienes el archivo Python completo con la lógica modificada y preservada, integrando las nuevas condiciones de `isinstance`, los cálculos de drawdown específicos y la gestión detallada de los *flips* (inversión de posición) para cumplir con los requisitos de seguridad del Risk Manager.

```python
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Any

# Importaciones simuladas o existentes en tu entorno (ajusta según necesidad real)
# from modules.risk_manager import RiskManager
# from modules.trade_reason import TradeReason
# from utils.slippage_config import SlippageConfig
# from utils.commission_config import CommissionConfig

log = logging.getLogger(__name__)

def process_symbol_trades(
    sym: str,
    holdings: Dict[str, int],
    cash: float,
    price: float,
    dt: datetime,
    returns: List[Any],
    equity_curve: List[Tuple[datetime, float]], # [Tiempo, Equity]
    cooldown_until: Dict[str, Any],
    rebalance_band_pct: float,
    risk_manager: Optional[RiskManager], # Asumimos que es una instancia o None
    risk_cost_bps: float,
    benefit_bps: float,
    slippage_cfg: SlippageConfig,
    commission_cfg: CommissionConfig,
    nav_prev: float,
    avg_price: Dict[str, float],
    last_targets: Dict[str, int],
    is_emergency: bool,
    force_close: bool,
    open_now: Dict[str, float], # Precio de apertura actual para cálculo de drawdown
):
    """
    Función que procesa la decisión de trade para un símbolo específico.
    
    Incluye:
    1. Check de cooldown.
    2. Gate de pérdida diaria anterior (Daily-loss hard-gate).
    3. Gate de Drawdown actual en el open-equity.
    4. Lógica de rebalanceo y bandas.
    5. Cálculo de beneficios vs costos (slippage/comision/risk cost).
    6. Gestión avanzada del Risk Manager con soportes para FLIPS (Cambio de posición).
    """

    delta = 0 # Delta deseado (cambio en la posición)
    target = 0 # Posición objetivo después del ajuste
    
    pos = holdings.get(sym, 0)
    
    # --- 1. Check de Cooldown ---
    if cooldown_until[sym] is not None and isinstance(cooldown_until[sym], int):
        if i < cooldown_until[sym]: # Nota: 'i' debe estar definido en el contexto del bucle principal
            delta = 0
            target = pos
            
    # Nota: Si 'i' no está disponible, la lógica depende de tu controlador principal.
    # Asumiendo que se pasa la posición deseada o se calcula aquí antes de entrar a las checks.
    
    # Ajustamos la variable 'i' para este contexto si fuera necesario, 
    # pero manteniendo el código limpio según tu fragmento proporcionado.
    # En tu snippet original, 'i' parece ser un índice global. Aquí asumimos que 
    # ya se calculó el delta objetivo inicial antes de entrar en las checks de riesgo.
    
    if delta == 0: # Reset si no hay movimiento planned inicialmente (por lógica anterior)
        # Re-assignación implícita basada en tu snippet original donde 'delta' podría venir de fuera
        pass 

    # --- 2. Daily-loss hard-gate (Basado en la pérdida del día anterior) ---
    if risk_manager is not None and delta != 0:
        try:
            # Preferimos equity_curve chain para evitar depender de las listas 'returns' internas si están vacías/inconsistentes
            if len(equity_curve) >= 2:
                eq_y = float(equity_curve[-1][1])       # Equity al cierre del día anterior (o inicio actual)
                eq_y_1 = float(equity_curve[-2][1])     # Equity del cierre anterior
                prev_ret = (eq_y / eq_y_1 - 1.0) if eq_y_1 != 0 else 0.0
            else:
                # Fallback a returns si no hay curva de equidad reciente
                if returns and len(returns) > 0:
                    # Ajusta esto según el formato real de 'returns' (asumido que tiene precios o retornos directos)
                    prev_ret = float(returns[-1][1]) if returns else 0.0 
                else:
                    prev_ret = 0.0
            
            limit_pct = abs(risk_manager.cfg.daily_loss_limit_pct) / 100.0
            
            # Si la pérdida anterior es mayor o igual al límite diario permitido
            if prev_ret <= -limit_pct:
                # Bloquear exposición incrementadora (entradas o aumentos de posición en short)
                # Permitir cerrar posiciones para recuperar margen (opcional, depende de tu estrategia exacta)
                # Según tu lógica: si pos == 0 NO hace nada. Si pos != 0 y el movimiento es hacia la pérdida actual (o similar), bloquea.
                exposure_increasing = True 
                
                if exposure_increasing:
                    delta = 0
                    target = pos
                    
        except Exception as e:
            log.warning(f"Error calculando prev_ret para daily-loss gate: {e}")
            pass
            
    # --- 3. Hard gate: Drawdown restriction en el open-equity ---
    if risk_manager is not None and delta != 0:
        try:
            # Evaluar drawdown en el valor de la cartera al momento de apertura actual (open_now)
            # Calculamos el Equity basado en Cash + Holdings * PrecioAbiertoActual
            eq_open_now = cash + sum(holdings[s] * open_now.get(s, 0.0) for s in holdings)
            
            # Verificamos si la restricción de drawdown está activa y activa
            ok_dd, msg_dd = risk_manager.check_drawdown(float(eq_open_now))
            
            # Determinar si el movimiento es "exposición creciente"
            exposure_increasing = False
            if pos == 0 and delta != 0:
                exposure_increasing = True # Entrada desde cero (apalancamiento)
            elif pos != 0:
                # Aumentar posición larga o aumentar tamaño short
                if (pos > 0 and delta > 0) or (pos < 0 and delta < 0):
                    exposure_increasing = True
            
            if not ok_dd and exposure_increasing:
                log.warning("Drawdown restriction active at open, blocking order.")
                delta = 0
                target = pos
                
        except Exception as e:
            log.error(f"Error en check_drawdrawdd para sym={sym}: {e}")
            pass

    # Si el riesgo bloqueó completamente el movimiento
    if delta == 0:
        continue
        
    # --- 4. Rebalance Band Check (Opcional, si existe configuración de rebalanceo) ---
    if pos != 0 and rebalance_band_pct > 0:
        # Evitar división por cero o números muy pequeños
        divisor = max(1, abs(pos))
        rel_change = abs(delta) / divisor
        
        if rel_change < rebalance_band_pct:
            continue
            
    side = 1 if delta > 0 else -1
    
    # --- 5. Estimación de costos y beneficios ---
    fill_price = _slip(slippage_cfg, price, side) # Función auxiliar simulada
    commission = _commission(commission_cfg, delta, fill_price) # Función auxiliar simulada
    
    if ((benefit_bps > 0.0) or (risk_cost_bps > 0.0)) and (pos != 0) and (target != 0) and (pos * target > 0):
        slippage_cost = abs(delta) * fill_price * (slippage_cfg.bps / 10000.0)
        risk_cost = abs(delta) * fill_price * (risk_cost_bps / 10000.0)
        
        # Estimación de beneficio esperado (simplificado aquí, usualmente viene de un modelo)
        expected_benefit = abs(delta) * fill_price * (benefit_bps / 10000.0)
        total_cost = commission + slippage_cost + risk_cost
        
        if expected_benefit <= total_cost:
            log.info(
                "no_rebalance delta=%s sym=%s exp_benefit=%.4f total_cost=%.4f",
                int(delta),
                sym,
                expected_benefit,
                total_cost,
            )
            continue
            
    # --- 6. Gestión de Risk Manager y Handling de FLIPS ---
    
    if risk_manager is not None:
        eq_prev = nav_prev # Valor anterior a la sesión
        
        # Calcular Equity actual al inicio (abriendo posición) para el riesgo diario
        eq_open = cash + sum(holdings[s] * open_now.get(s, 0.0) for s in holdings)
        
        # Calcular valor de la posición actual antes del trade
        cur_pos_val = sum(hold