from __future__ import annotations

import typing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Sentinel para 'no symbol' cuando se pide el primer equity válido
_NO_SYMBOL = object()


def _last_close_series(prices: Dict[str, pd.DataFrame], *, symbol: str) -> Optional[pd.Series]:
    """Devuelve la Serie del último cierre (o vacío si no hay datos o fechas > as_of)."""
    df = prices.get(symbol)
    if df is None or len(df) == 0:
        return None

    # Filtrar hasta el día de corte (inclusive)
    cutoff_date = _to_datetime(prices) if (as_of := getattr(globals(), "as_of")) else datetime.now()
    # Ajuste: la variable as_of debe estar disponible o usar default. 
    # Como es un helper local y no tenemos 'as_of' en scope global directamente aquí, 
    # lo pasamos como parámetro implícito al llamarlo desde build_market_radar.
    # REFACTORIZACION PARA CORRECTO: Pasar as_of a helpers o usar variable de contexto.
    # Para mantener la firma limpia, asumiremos que el contexto tiene 'as_of' definido en build_market_radar
    # y lo pasamos explícitamente aquí para seguridad tipada.
    
    # Nota: Este helper necesita saber el cutoff. Lo manejaremos dentro de build_market_radar
    # para evitar dependencias externas al scope del archivo si no se pasa.
    return None


def _last_close_series_v2(prices: Dict[str, pd.DataFrame], symbol: str, as_of: Optional[pd.Timestamp]) -> Optional[pd.Series]:
    """Devuelve la Serie de precios filtrada hasta el momento as_of (inclusive)."""
    if as_of is None:
        as_of = prices[list(prices.keys())[0]].index[-1] if prices else pd.Timestamp.now() - pd.Timedelta(days=1)

    # Si as_of es None y hay datos, usamos el último cierre disponible como corte (snapshot "now")
    if as_of is None:
        last_available = next((p.index[-1] for p in prices.values() if len(p) > 0), None)
        if last_available:
            as_of = last_available

    df = prices.get(symbol)
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)

    # Asegurar que el índice es datetime
    idx = df.index
    if not isinstance(idx[0], (pd.Timestamp, datetime)):
        df.index = pd.to_datetime(df.index)
    
    # Filtrar rows <= as_of
    mask = idx <= as_of
    filtered_df = df[mask]
    
    return filtered_df.set_index(filtered_df.index)


def _ma(prices: Dict[str, pd.DataFrame], *, symbol: str, period: int) -> Optional[pd.Series]:
    """Calcula la media móvil simple de la Serie dada."""
    series = _last_close_series_v2(prices, symbol, getattr(globals(), 'as_of')) # Error lógico en scope.
    # Corrección robusta: El código final debe pasar as_of explícitamente o tenerlo en scope.
    # Para la implementación final segura, usaremos una variable de contexto o pass-by-value.
    # Dado que esto es un archivo autocontenido, usaremos la variable 'as_of' definida en el scope de build_market_radar.
    pass


def _ma_fixed(series: pd.Series, period: int) -> Optional[pd.Series]:
    """Calcula MA."""
    if series is None or len(series) < period:
        return pd.Series(dtype=float)
    # Asegurar ordenamiento por fecha (el índice ya debería serlo al crear el DataFrame de precios)
    s = series.dropna()
    if len(s) < period:
        return pd.Series(dtype=float)
    return s.rolling(window=period, min_periods=1).mean()


def _ann_vol(series: pd.Series, *, risk_free_rate: float = 0.02, annualization_factor: float = 252) -> Optional[float]:
    """Calcula volatilidad anualizada de una Serie de retornos."""
    if series is None or len(series) < 2:
        return None

    # Retornos logarítmicos diarios (aproximado con simple si no hay división, asumimos 'close')
    # La serie pasada aquí es de PRECIOS o RETORNOS? 
    # En el contexto del radar, _last_close_series devuelve precios.
    # Para calcular volatilidad, necesitamos retornos.
    returns = series.pct_change().dropna()
    
    if len(returns) == 0:
        return None

    # Volatilidad diaria (desviación estándar)
    daily_vol = returns.std()
    
    # Volatilidad anualizada = daily_vol * sqrt(dias/año)
    annual_vol = daily_vol * np.sqrt(annualization_factor)
    
    # Ajuste por tasa libre de riesgo si se requiere exceso, pero "volatilidad del activo" es std.
    # El prompt dice "vol anualizada 20d de retornos SPY". Eso es simplemente std annualizado.
    return float(annual_vol)


def _to_datetime(prices: Dict[str, pd.DataFrame]) -> Optional[pd.Timestamp]:
    """Obtiene el último cierre disponible del primer símbolo."""
    first_sym = next(iter(prices), None)
    if not first_sym:
        return None
    df = prices[first_sym]
    if len(df) == 0:
        return None
    return df.index[-1]


def build_market_radar(
    prices: Dict[str, pd.DataFrame],
    *,
    as_of: Optional[pd.Timestamp] = None
) -> Dict[str, Any]:
    """
    Snapshot honesto del estado de mercado a as_of (último índice común si None).
    
    Usa solo barras <= as_of. Sin claims de alpha. 
    Campos:
      - as_of: ISO date
      - equity_trend: +1/0/-1 si SPY o primer equity close > / ~ / < MA100
      - equity_vol_20: vol anualizada 20d de retornos SPY (o primer símbolo)
      - risk_on_proxy: 1 si VIX disponible y VIX < MA50; else None
      - rates_slope: TLT vs IEF 20d return differential si ambos existen; else None
      - commodity_momentum: GLD o PDBC 60d return si existe
      - breadth_proxy: fracción de símbolos con close > MA50 entre los que tienen >=50 barras
      - notes: lista corta de strings (faltan símbolos, etc.)
      - disclaimer: "Triage only. Not a buy list. Not predictive of returns."
    """

    # Determinar as_of final si no se proporciona
    if as_of is None:
        # Buscar el último cierre en cualquier dataframe disponible
        last_date = _to_datetime(prices)
        if last_date:
            as_of = last_date
        else:
            # Caso vacío
            pass

    # 1. Identificar símbolos clave (Normalización de nombres)
    def get_key(series_name: str, candidates: List[str]) -> Optional[str]:
        """Intenta encontrar una coincidencia en las claves 'candidates'."""
        for cand in candidates:
            if cand.lower() in series_name.lower() or series_name.lower() in cand.lower():
                return cand # O el nombre exacto del diccionario que coincide
        return None

    # Intentar mapear símbolos conocidos a las claves existentes en 'prices'
    # Asumimos que las claves de 'prices' son strings. Buscamos por subcadena o igualdad.
    
    # Mapeo de SPY
    spy_key = get_key(next(iter(prices.keys())) if prices else None, ["SPY", "US_SP500"])
    # Si no encontramos SPY explícito, usamos el primer símbolo como proxy del mercado si tiene sentido (aunque el prompt pide SPY o primero)
    if not spy_key:
        # Intentar encontrar cualquier equidad grande
        for key in sorted(prices.keys(), key=lambda x: -len(x)): # Preferir nombres largos primero? No, prefirer precisión.
            # Lógica simple: tomar el primer que parezca un índice bursátil o ETF principal
            # Para este snapshot honesto, si no hay SPY, usamos el primer activo disponible como "equity"
            spy_key = key 
            break

    # Mapeo de VIX (si existe en los datos)
    vix_candidates = ["VIX", "^VIX", "CBOE_VIX"]
    vix_key = get_key(None, vix_candidates)
    if not vix_key:
        # Buscar claves que contengan 'vix' o '^vix' case insensitive
        for k in prices.keys():
            if 'vix' in k.lower() or k.startswith('^'):
                vix_key = k
                break

    # Mapeo de bonos (TLT, IEF)
    bond_candidates_long = ["TLT", "US30Y"]
    tlt_key = get_key(None, bond_candidates_long)
    ief_candidates = ["IEF", "US7-10Y"]
    ief_key = get_key(None, ief_candidates)

    # Commodity (GLD, PDBC)
    gold_candidates = ["GLD", "PDBC", "GC", "HUI"] # HUI es indice, mejor GLD/PDBC
    gold_key = get_key(None, gold_candidates)

    # 2. Procesar SPY (o primer equity)
    series_equity = _last_close_series_v2(prices, spy_key or next(iter(prices.keys()), "UNKNOWN"), as_of)
    
    trend_val = None
    vol_val = None
    
    if series_equity is not None:
        # MA100 (o lo que sea razonable si < 100 dias)
        ma_series = _ma_fixed(series_equity, period=100)
        current_ma = ma_series[series_equity.index[-1]] if len(ma_series) > 0 else None
        current_close = series_equity.iloc[-1] # El último cierre filtrado
        
        if current_ma is not None and pd.notna(current_close):
            trend_val = 1 if current_close > current_ma else (-1 if current_close < current_ma else 0)
            
            # Volatilidad 20 días
            # Necesitamos retornos. El dataframe original en 'prices' probablemente tiene cierre, alta, baja, volumen.
            # Asumimos que series_equity es un DF o Series de precios.
            # Para calcular vol de 20 dias, usamos los ultimos 20 dias disponibles en la serie filtrada?
            # El prompt dice "vol anualizada 20d de retornos SPY". 
            # Calculamos std de los ultimos 20 retornos diarios * sqrt(252)
            
            if len(series_equity) >= 2:
                rets = series_equity.pct_change().dropna()
                # Filtrar solo los ultimos 20 dias de datos disponibles hasta as_of
                recent_len = min(len(rets), 20)
                if recent_len > 1:
                    recent_rets = rets.tail(recent_len)
                    daily_vol = recent_rets.std()
                    vol_val = float(daily_vol * np.sqrt(252))
    
    # 3. Procesar VIX (Risk On)
    risk_on_proxy = None
    if vix_key and vix_key in prices:
        series_vix = _last_close_series_v2(prices, vix_key, as_of)
        if series_vix is not None:
            # MA50 de VIX
            ma_50_vix = _ma_fixed(series_vix, period=50)
            current_vix = series_vix.iloc[-1] if len(series_vix) > 0 else None
            ma_val_vix = ma_50_vix[series_vix.index[-1]] if len(ma_50_vix) > 0 else None
            
            if current_vix is not None and pd.notna(current_vix) and pd.notna(ma_val_vix):
                # Riesgo bajo (Risk On) si VIX < MA50
                risk_on_proxy = 1 if current_vix < ma_val_vix else None

    # 4. Procesar Bonos (Rates Slope)
    rates_slope = None
    if tlt_key and tlt_key in prices and ief_key and ief_key in prices:
        # Necesitamos retornos diferenciales de 20 dias? O simplemente niveles?
        # "TLT vs IEF 20d return differential".
        # TLT (long), IEF (short). Spread = Yield_short - Yield_long o Price_long - Price_short.
        # Generalmente, slope negativo es riesgo bajo? Depende de la convención.
        # Retorno TLT menos Retorno IEF en 20 dias.
        
        s_tlt = _last_close_series_v2(prices, tlt_key, as_of)
        s_ief = _last_close_series_v2(prices, ief_key, as_of)
        
        if s_tlt is not None and s_ief is not None:
            # Retornos diarios
            r_tlt = s_tlt.pct_change().dropna()
            r_ief = s_ief.pct_change().dropna()
            
            # Diferencial de 20 dias (promedio o sum?) "differential". Usaremos promedio para nivel, o sum?
            # Usually spread is yield diff. Here we use price return diff for simplicity in momentum context.
            # Let's calculate average daily return diff over last 20 days where both exist.
            len_common = min(len(r_tlt), len(r_ief))
            if len_common >= 1:
                tail_len = min(len_common, 20)
                common_rets = r_tlt.tail(tail_len).fillna(0) # Asumir 0 si faltan (riesgoso pero ok para snapshot simple)
                # Mejor intersectar indices o tomar los ultimos N de ambos.
                # Simplificacion: tomamos los ultimos N dias disponibles del conjunto más grande y asumimos el otro si falta?
                # No, mejor interseccion limpia.
                common_dates = r_tlt.index.intersection(r_ief.index)
                if len(common_dates) >= 1:
                    diff_series = (r_tlt[common_dates] - r_ief[common_dates])
                    slope_val = float(diff_series.mean()) # O suma? "differential" usually implies level of difference. 
                    # Si es momentum, el cambio en el spread. 
                    # Usamos el promedio de la diferencia diaria como proxy del nivel del spread reciente.
                    rates_slope = slope_val
    
    # 5. Commodity Momentum
    commodity_momentum = None
    if gold_key and gold_key in prices:
        s_gold = _last_close_series_v2(prices, gold_key, as_of)
        if s_gold is not None and len(s_gold) >= 60:
            # Retorno acumulado de 60 dias
            # Retorno logaritmico total o simple? Simple.
            first_val = s_gold.iloc[s_gold.index[-60]]
            last_val = s_gold.iloc[-1]
            if pd.notna(first_val) and pd.notna(last_val):
                commodity_momentum = float((last_val - first_val) / first_val)
        elif len(s_gold) < 60:
            # Si no hay 60 dias, usamos lo que haya? El prompt dice "si existe". Asumimos requiere >=60 o calcular con lo disponible.
            # "GLD o PDBC 60d return si existe". Si no tiene 60 dias de datos hasta ahora, retornar None?
            # O calculo relativo a inicio de serie?
            # Para robustez: calcular retorno desde el cierre mas antiguo disponible hasta as_of.
            first_val = s_gold.iloc[0]
            last_val = s_gold.iloc[-1]
            if pd.notna(first_val) and pd.notna(last_val):
                commodity_m