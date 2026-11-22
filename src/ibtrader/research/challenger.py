"""Retador contra titular: ¿una variante le gana de verdad a la estrategia que ya corre en paper?

Comparar dos Sharpe sueltos no sirve: con 18 años de datos diarios el error estándar de un Sharpe es
de unos 0,24, así que una diferencia de 0,1 entre dos variantes es ruido. Pero las dos estrategias
operan los mismos días y los mismos ETF, y sus retornos están muy correlacionados. La prueba
**pareada** mira la diferencia día a día y por eso distingue mucho mejor.

Método:

* Titular y retadores corren con el mismo motor, costes y gestor de riesgo que ``research-portfolio``.
* Ventana común: desde el calentamiento más tardío hasta la última barra.
* Sharpe sobre el **exceso** contra el ETF de letras del Tesoro (BIL), no contra cero.
* Bootstrap por bloques circulares (bloques de 21 sesiones, para respetar la autocorrelación) sobre
  los pares de retornos: intervalo de confianza de la diferencia de Sharpe y de retorno anual.
* Corrección de Bonferroni: con ``m`` retadores el intervalo se calcula al ``1 - 0,05/m``.
* Veredicto ``promover`` solo si todo el intervalo de la diferencia de Sharpe queda por encima de 0.
  ``peor`` si queda por debajo. En otro caso, ``indistinguible``: no se cambia la producción.

Los **perfiles de riesgo** (``box_budgets``) no buscan más Sharpe: mueven riesgo de bonos a acciones
para usar la caída que Adam tolera. Las **mezclas** dejan una parte fija del capital en un núcleo
pasivo 60/40 y el resto en la tendencia: son dos fuentes de retorno poco correlacionadas (la prima
de acciones y bonos, y la tendencia). Se informan con el mismo método, pero la parte de núcleo se
elige por tolerancia a la caída, no por el resultado del backtest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..backtest.engine import backtest
from ..config import AppSettings
from ..data.universe import UniverseSpec
from ..engine.targets import min_trade_frac_for
from ..pipeline.rules import CROSS_SECTIONAL_RULES, DEFAULT_RULES
from ..pipeline.system import SystemConfig
from ..risk.manager import RiskManager, RiskState
from ..strategy.pipeline_strategy import PipelineStrategy
from .benchmarks import sixty_forty
from .portfolio_runner import (
    BENCHMARK_COST_BPS,
    BENCHMARK_REBALANCE,
    CORE_TREND_RULES,
    CORE_TREND_WEIGHTS,
    INITIAL_EQUITY,
    _window_stats,
    close_frame,
    sixty_forty_legs,
)

TRADING_DAYS = 252
BLOCK_DAYS = 21
N_BOOTSTRAP = 2000
ALPHA = 0.05
SEED = 0

#: Clase de activo del universo → grupo de riesgo de los perfiles.
RISK_GROUPS: Dict[str, str] = {
    "equity": "acciones",
    "fixed_income": "bonos",
    "commodity": "reales",
    "real_estate": "reales",
}

#: Reparto del riesgo por grupo. ``actual`` (un tercio cada uno) es lo que hoy corre en paper.
RISK_PROFILES: Dict[str, Dict[str, float]] = {
    "perfil_equilibrado": {"acciones": 0.50, "bonos": 0.25, "reales": 0.25},
    "perfil_crecimiento": {"acciones": 0.60, "bonos": 0.20, "reales": 0.20},
}


@dataclass(frozen=True)
class Contender:
    """Una configuración del pipeline. ``kind``: ``variante`` (ya probada) o ``perfil`` (dial de riesgo)."""

    cid: str
    rules: Tuple[str, ...] = tuple(DEFAULT_RULES)
    weighting: str = "box_risk_parity"
    rule_weights: Optional[Dict[str, float]] = None
    group_budgets: Optional[Dict[str, float]] = None
    kind: str = "variante"
    extra: Dict[str, Any] = field(default_factory=dict)


#: Núcleo pasivo de las mezclas: el 60/40 de referencia (acciones de EE. UU. y bonos del Tesoro a 7-10 años).
CORE_60_40: Dict[str, float] = {"SPY": 0.60, "IEF": 0.40}

#: Lo que corre en paper: ``STRATEGY__PARAMS={}`` = reglas por defecto y riesgo igual por ETF.
INCUMBENT = Contender("titular_tendencia_riesgo_igual")

#: Fase 3: mitad del pronóstico para la tendencia (cuatro reglas a partes iguales) y mitad para el
#: momentum relativo. Reparto por familias fijado antes de correr la prueba.
RELMOM_RULES: Tuple[str, ...] = (*DEFAULT_RULES, "relmom_1_3_12")
RELMOM_WEIGHTS: Dict[str, float] = {
    **{r: 0.5 / len(DEFAULT_RULES) for r in DEFAULT_RULES}, "relmom_1_3_12": 0.5,
}
PAPER_MIX = Contender("paper_nucleo_25_tendencia_75", kind="mezcla",
                      extra={"core_weights": dict(CORE_60_40), "core_frac": 0.25})
RELMOM_CHALLENGER = Contender(
    "paper_mas_momentum_relativo", rules=RELMOM_RULES, rule_weights=dict(RELMOM_WEIGHTS), kind="familia",
    extra={"core_weights": dict(CORE_60_40), "core_frac": 0.25},
)

#: Fase 3, carry: mismo reparto por familias que el momentum relativo, fijado antes de correr.
CARRY_RULES: Tuple[str, ...] = (*DEFAULT_RULES, "carry_12m")
CARRY_WEIGHTS: Dict[str, float] = {**{r: 0.5 / len(DEFAULT_RULES) for r in DEFAULT_RULES}, "carry_12m": 0.5}
CARRY_CHALLENGER = Contender(
    "paper_mas_carry", rules=CARRY_RULES, rule_weights=dict(CARRY_WEIGHTS), kind="familia",
    extra={"core_weights": dict(CORE_60_40), "core_frac": 0.25},
)

#: Lista fijada **antes** de mirar resultados. Las tres variantes ya estaban en el registro de pruebas.
DEFAULT_CHALLENGERS: Tuple[Contender, ...] = (
    Contender("ewmac_hrp", rules=tuple(r for r in DEFAULT_RULES if r.startswith("ewmac")), weighting="hrp"),
    Contender("paridad_sin_timing", rules=("long_const",)),
    Contender("nucleo_mas_tendencia", rules=CORE_TREND_RULES, rule_weights=dict(CORE_TREND_WEIGHTS)),
    Contender("perfil_equilibrado", group_budgets=RISK_PROFILES["perfil_equilibrado"], kind="perfil"),
    Contender("perfil_crecimiento", group_budgets=RISK_PROFILES["perfil_crecimiento"], kind="perfil"),
    Contender("nucleo_25_tendencia_75", kind="mezcla", extra={"core_weights": dict(CORE_60_40), "core_frac": 0.25}),
    Contender("nucleo_50_tendencia_50", kind="mezcla", extra={"core_weights": dict(CORE_60_40), "core_frac": 0.50}),
)


def peer_groups_from_universe(universe: UniverseSpec, symbols: Sequence[str]) -> Dict[str, str]:
    """Símbolo → grupo de pares (``RISK_GROUPS`` de su clase de activo). El efectivo no tiene pares."""
    out: Dict[str, str] = {}
    for e in universe.entries:
        group = RISK_GROUPS.get(e.asset_class.lower())
        if e.symbol in symbols and group is not None:
            out[e.symbol] = group
    return out


def box_budgets_from_groups(
    universe: UniverseSpec, symbols: Sequence[str], group_budgets: Mapping[str, float]
) -> Dict[str, float]:
    """Presupuesto por caja: el del grupo, repartido a partes iguales entre las cajas del grupo.

    Las cajas de efectivo (clase ``cash``) no entran. Una clase de activo sin grupo en
    ``RISK_GROUPS`` es un error: no se le asigna riesgo en silencio.
    """
    boxes_by_group: Dict[str, List[str]] = {}
    for e in universe.entries:
        if e.symbol not in symbols or e.asset_class.lower() == "cash":
            continue
        group = RISK_GROUPS.get(e.asset_class.lower())
        if group is None:
            raise ValueError(f"clase de activo sin grupo de riesgo: {e.asset_class!r} ({e.symbol})")
        if e.box not in boxes_by_group.setdefault(group, []):
            boxes_by_group[group].append(e.box)
    out: Dict[str, float] = {}
    for group, boxes in boxes_by_group.items():
        share = float(group_budgets.get(group, 0.0)) / len(boxes)
        for b in boxes:
            out[b] = share
    if sum(out.values()) <= 0.0:
        raise ValueError("los presupuestos por grupo no asignan riesgo a ninguna caja del universo")
    return out


# --------------------------------------------------------------------------- estadística


def _sharpe(excess: np.ndarray) -> float:
    sd = float(excess.std(ddof=1))
    if not (sd > 0.0 and math.isfinite(sd)):
        return float("nan")
    return float(excess.mean()) / sd * math.sqrt(TRADING_DAYS)


def _max_drawdown(returns: np.ndarray) -> float:
    eq = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min()) if len(eq) else 0.0


def _cagr(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return float("nan")
    total = float(np.prod(1.0 + returns))
    return float(total ** (TRADING_DAYS / len(returns)) - 1.0) if total > 0 else float("nan")


def summary(returns: pd.Series, cash: pd.Series) -> Dict[str, float]:
    """CAGR, volatilidad, Sharpe sobre el exceso contra ``cash`` y caída máxima."""
    r = returns.to_numpy(dtype=float)
    ex = r - cash.reindex(returns.index).fillna(0.0).to_numpy(dtype=float)
    return {
        "cagr": _cagr(r),
        "vol": float(r.std(ddof=1)) * math.sqrt(TRADING_DAYS),
        "sharpe_exceso": _sharpe(ex),
        "max_drawdown": _max_drawdown(r),
    }


def _block_indices(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Índices de ``n_boot`` remuestreos por bloques circulares de longitud ``block``."""
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    return idx.reshape(n_boot, -1)[:, :n]


def paired_comparison(
    incumbent: pd.Series,
    challenger: pd.Series,
    cash: pd.Series,
    *,
    n_comparisons: int = 1,
    block: int = BLOCK_DAYS,
    n_boot: int = N_BOOTSTRAP,
    alpha: float = ALPHA,
    seed: int = SEED,
) -> Dict[str, Any]:
    """Diferencia retador − titular en la ventana común, con intervalo por bootstrap de bloques.

    ``n_comparisons`` es el número de retadores comparados en la misma tanda (Bonferroni).
    """
    frame = pd.DataFrame({"inc": incumbent, "cha": challenger}).dropna()
    n = int(len(frame))
    if n < 2 * TRADING_DAYS:
        return {"n_obs": n, "veredicto": "sin_datos", "nota": f"ventana común {n} < {2 * TRADING_DAYS} sesiones"}
    c = cash.reindex(frame.index).fillna(0.0).to_numpy(dtype=float)
    a = frame["inc"].to_numpy(dtype=float)
    b = frame["cha"].to_numpy(dtype=float)
    d_sharpe = _sharpe(b - c) - _sharpe(a - c)
    d_ret = float((b - a).mean()) * TRADING_DAYS
    rng = np.random.default_rng(seed)
    idx = _block_indices(n, block, n_boot, rng)
    ea, eb = (a - c)[idx], (b - c)[idx]
    sa = ea.mean(axis=1) / ea.std(axis=1, ddof=1) * math.sqrt(TRADING_DAYS)
    sb = eb.mean(axis=1) / eb.std(axis=1, ddof=1) * math.sqrt(TRADING_DAYS)
    boot_sharpe = sb - sa
    boot_ret = (b - a)[idx].mean(axis=1) * TRADING_DAYS
    level = alpha / max(1, int(n_comparisons))
    lo, hi = 100.0 * level / 2.0, 100.0 * (1.0 - level / 2.0)
    ci_s = (float(np.nanpercentile(boot_sharpe, lo)), float(np.nanpercentile(boot_sharpe, hi)))
    ci_r = (float(np.nanpercentile(boot_ret, lo)), float(np.nanpercentile(boot_ret, hi)))
    if ci_s[0] > 0.0:
        verdict = "promover"
    elif ci_s[1] < 0.0:
        verdict = "peor"
    else:
        verdict = "indistinguible"
    return {
        "n_obs": n,
        "correlacion": float(np.corrcoef(a, b)[0, 1]),
        "dif_sharpe": d_sharpe,
        "ic_dif_sharpe": ci_s,
        "dif_retorno_anual": d_ret,
        "ic_dif_retorno_anual": ci_r,
        "prob_retador_mejor_sharpe": float(np.mean(boot_sharpe > 0.0)),
        "nivel_confianza": 1.0 - level,
        "n_comparaciones": int(n_comparisons),
        "veredicto": verdict,
    }


#: Pruebas de estrés fijas del plan maestro (fase 1): de máximo a mínimo del S&P 500 en cada crisis.
STRESS_WINDOWS: Dict[str, Tuple[str, str]] = {
    "crisis_2008": ("2007-10-09", "2009-03-09"),
    "covid_2020": ("2020-02-19", "2020-03-23"),
    "inflacion_2022": ("2022-01-03", "2022-10-14"),
}


def stress_report(returns: pd.Series) -> Dict[str, Dict[str, float]]:
    """Retorno total, peor caída y peor mes natural dentro de cada ventana de ``STRESS_WINDOWS``.

    Una ventana que no cae entera dentro de ``returns`` se omite: no se informa media crisis.
    """
    out: Dict[str, Dict[str, float]] = {}
    if returns.empty:
        return out
    for name, (a, b) in STRESS_WINDOWS.items():
        start, end = pd.Timestamp(a), pd.Timestamp(b)
        if returns.index.min() > start or returns.index.max() < end:
            continue
        r = returns.loc[start:end]
        monthly = (1.0 + r).groupby([r.index.year, r.index.month]).prod() - 1.0
        out[name] = {
            "retorno_total": float(np.prod(1.0 + r.to_numpy(dtype=float)) - 1.0),
            "caida_max": _max_drawdown(r.to_numpy(dtype=float)),
            "peor_mes": float(monthly.min()),
        }
    return out


def settings_with_universe_spreads(settings: AppSettings, universe: UniverseSpec) -> AppSettings:
    """Copia de ``settings`` con el spread por símbolo que declara el universo (no muta el original)."""
    out = settings.model_copy(deep=True)
    merged = dict(out.slippage.spread_bps_by_symbol or {})
    for e in universe.entries:
        if e.spread_bps is not None:
            merged[e.symbol] = float(e.spread_bps)
    out.slippage.spread_bps_by_symbol = merged
    return out


# --------------------------------------------------------------------------- el estudio


def _run(
    c: Contender, data: Mapping[str, pd.DataFrame], settings: AppSettings, universe: UniverseSpec,
    boxes: Dict[str, str], symbols: Sequence[str],
) -> Tuple[pd.Series, Optional[pd.Timestamp], Dict[str, Any]]:
    capital = INITIAL_EQUITY
    budgets = box_budgets_from_groups(universe, symbols, c.group_budgets) if c.group_budgets else None
    peers = peer_groups_from_universe(universe, symbols) if set(c.rules) & set(CROSS_SECTIONAL_RULES) else None
    cfg = SystemConfig(
        peer_groups=peers, rules=tuple(c.rules), rule_weights=c.rule_weights, instrument_weighting=c.weighting,  # type: ignore[arg-type]
        boxes=boxes, box_budgets=budgets, capital=capital, long_only=True, max_leverage=1.0,
        min_trade_frac=min_trade_frac_for(settings, capital), **c.extra,
    )
    strategy = PipelineStrategy(cfg)
    res = backtest(
        data=dict(data), strategy=strategy, commission_cfg=settings.commission,
        slippage_cfg=settings.slippage, initial_equity=capital, direction="long_only",
        risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=capital)),
        reg_fees_cfg=settings.reg_fees,
    )
    out = strategy.last_output
    start = out.warmup_end if out is not None else None
    costs: Dict[str, Any] = {}
    if start is not None:
        st = _window_stats(res, start, capital)
        costs = {"coste_operar_anual_pct": st.get("cost_drag_annual_pct"),
                 "rotacion_anual": st.get("turnover_annual")}
        if out is not None and len(out.target_weights):
            w = out.target_weights.loc[start:]
            cash_cols = [s for s in cfg.cash_symbols(list(w.columns)) if s in w.columns]
            costs["peso_medio_efectivo"] = float(w[cash_cols].sum(axis=1).mean()) if cash_cols else 0.0
            by_group: Dict[str, float] = {}
            for e in universe.entries:
                g = RISK_GROUPS.get(e.asset_class.lower())
                if g and e.symbol in w.columns:
                    by_group[g] = by_group.get(g, 0.0) + float(w[e.symbol].mean())
            costs["peso_medio_por_grupo"] = by_group
    return res.returns.astype(float), start, costs


def run_challenger_study(
    data: Mapping[str, pd.DataFrame],
    settings: AppSettings,
    universe: UniverseSpec,
    *,
    incumbent: Contender = INCUMBENT,
    challengers: Sequence[Contender] = DEFAULT_CHALLENGERS,
    n_boot: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> Dict[str, Any]:
    """Corre titular y retadores, los recorta a la ventana común y compara cada retador con el titular."""
    prices = close_frame(dict(data))
    symbols = list(prices.columns)
    boxes = {e.symbol: e.box for e in universe.entries if e.symbol in symbols}
    runs: Dict[str, Tuple[pd.Series, Dict[str, Any]]] = {}
    starts: List[pd.Timestamp] = []
    for c in (incumbent, *challengers):
        rets, start, costs = _run(c, data, settings, universe, boxes, symbols)
        if start is None:
            raise ValueError(f"{c.cid}: el sistema no termina el calentamiento con estos datos")
        runs[c.cid] = (rets, costs)
        starts.append(start)
    window_start = max(starts)

    def _cut(r: pd.Series) -> pd.Series:
        w = r.loc[window_start:]
        return w.iloc[1:] if len(w) else w  # el retorno de la primera barra es del libro de calentamiento

    cash_syms = [e.symbol for e in universe.entries if e.asset_class.lower() == "cash" and e.symbol in symbols]
    cash = (prices[cash_syms[0]].ffill().pct_change().fillna(0.0) if cash_syms
            else pd.Series(0.0, index=prices.index))
    inc_r = _cut(runs[incumbent.cid][0])
    rows: List[Dict[str, Any]] = [
        {"id": incumbent.cid, "tipo": "titular", **summary(inc_r, cash), **runs[incumbent.cid][1],
         "crisis": stress_report(inc_r)}
    ]
    for c in challengers:
        r = _cut(runs[c.cid][0])
        rows.append({
            "id": c.cid, "tipo": c.kind, **summary(r, cash), **runs[c.cid][1], "crisis": stress_report(r),
            "contra_titular": paired_comparison(inc_r, r, cash, n_comparisons=len(challengers),
                                                n_boot=n_boot, seed=seed),
        })
    # Referencia pasiva 60/40 en la misma ventana (mismo coste que usa research-portfolio).
    px = prices.ffill().loc[window_start:]
    eq_leg, bond_leg = sixty_forty_legs(list(px.columns), universe)
    sf = _cut(pd.Series(sixty_forty(px, equity=eq_leg, bonds=bond_leg, rebalance=BENCHMARK_REBALANCE,
                                    cost_bps=BENCHMARK_COST_BPS), dtype=float).reindex(px.index).fillna(0.0))
    rows.append({
        "id": "referencia_60_40", "tipo": "referencia", **summary(sf, cash), "crisis": stress_report(sf),
        "contra_titular": paired_comparison(inc_r, sf, cash, n_comparisons=len(challengers),
                                            n_boot=n_boot, seed=seed),
    })
    return {
        "nota": ("Comparación pareada contra la estrategia que corre en paper. Solo 'promover' justifica "
                 "cambiar la producción; los perfiles se eligen por tolerancia a la caída."),
        "desde": str(inc_r.index.min().date()) if len(inc_r) else None,
        "hasta": str(inc_r.index.max().date()) if len(inc_r) else None,
        "n_sesiones": int(len(inc_r)),
        "bloque_sesiones": BLOCK_DAYS,
        "n_bootstrap": int(n_boot),
        "titular": incumbent.cid,
        "filas": rows,
    }


def run_universe_study(
    data_incumbent: Mapping[str, pd.DataFrame],
    universe_incumbent: UniverseSpec,
    data_challenger: Mapping[str, pd.DataFrame],
    universe_challenger: UniverseSpec,
    settings: AppSettings,
    *,
    configs: Sequence[Contender],
    n_boot: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> Dict[str, Any]:
    """Mismo sistema, dos universos: ¿operar más mercados le gana al universo titular?

    Cada configuración de ``configs`` corre en los dos universos con el spread que declara cada uno.
    La ventana es común a todo (el calentamiento más tardío). El efectivo de referencia para el Sharpe
    es el ETF de letras del universo titular. Bonferroni sobre ``len(configs)`` comparaciones.
    """
    sides = {
        "titular": (data_incumbent, universe_incumbent),
        "retador": (data_challenger, universe_challenger),
    }
    runs: Dict[Tuple[str, str], Tuple[pd.Series, Dict[str, Any]]] = {}
    starts: List[pd.Timestamp] = []
    for side, (data, uni) in sides.items():
        st = settings_with_universe_spreads(settings, uni)
        symbols = list(close_frame(dict(data)).columns)
        boxes = {e.symbol: e.box for e in uni.entries if e.symbol in symbols}
        for c in configs:
            rets, start, costs = _run(c, data, st, uni, boxes, symbols)
            if start is None:
                raise ValueError(f"{c.cid} ({side}): el sistema no termina el calentamiento con estos datos")
            runs[(side, c.cid)] = (rets, costs)
            starts.append(start)
    window_start = max(starts)
    prices = close_frame(dict(data_incumbent))
    cash_syms = [e.symbol for e in universe_incumbent.entries
                 if e.asset_class.lower() == "cash" and e.symbol in prices.columns]
    cash = (prices[cash_syms[0]].ffill().pct_change().fillna(0.0) if cash_syms
            else pd.Series(0.0, index=prices.index))

    def _cut(r: pd.Series) -> pd.Series:
        return r.loc[window_start:].iloc[1:]

    rows: List[Dict[str, Any]] = []
    for c in configs:
        inc_r, cha_r = _cut(runs[("titular", c.cid)][0]), _cut(runs[("retador", c.cid)][0])
        rows.append({
            "config": c.cid,
            "titular": {**summary(inc_r, cash), **runs[("titular", c.cid)][1], "crisis": stress_report(inc_r)},
            "retador": {**summary(cha_r, cash), **runs[("retador", c.cid)][1], "crisis": stress_report(cha_r)},
            "contra_titular": paired_comparison(inc_r, cha_r, cash, n_comparisons=len(configs),
                                                n_boot=n_boot, seed=seed),
        })
    return {
        "nota": "Mismo sistema en dos universos. Solo 'promover' justifica cambiar el universo de producción.",
        "universo_titular": universe_incumbent.name,
        "universo_retador": universe_challenger.name,
        "desde": str(window_start.date()),
        "n_sesiones": int(len(_cut(runs[("titular", configs[0].cid)][0]))),
        "filas": rows,
    }


__all__ = [
    "CARRY_CHALLENGER", "CARRY_RULES", "CARRY_WEIGHTS", "CORE_60_40", "Contender",
    "DEFAULT_CHALLENGERS", "INCUMBENT", "PAPER_MIX", "RELMOM_CHALLENGER",
    "RELMOM_RULES", "RELMOM_WEIGHTS", "RISK_GROUPS", "RISK_PROFILES",
    "STRESS_WINDOWS", "box_budgets_from_groups", "paired_comparison", "peer_groups_from_universe",
    "run_challenger_study",
    "run_universe_study", "settings_with_universe_spreads", "stress_report", "summary",
]
