from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from ..config import AppSettings
from ..ensemble.combiner import (
    EnsembleWeights,
    apply_regime_filter,
    enforce_stops,
    score_strategies,
    score_to_position,
)
from ..intelligence.features import build_features
from ..intelligence.regime import detect_regime
from ..logging import setup_logging
from ..ops.journal import get_engine as get_journal_engine
from ..portfolio.sizing import volatility_target_weights
from ..risk.manager import RiskManager
from ..strategy.mean_reversion import MeanReversion
from ..strategy.sma_crossover import SMACrossover
from .paper_policy import (
    apply_stop_veto,
    classify_paper_action,
    size_paper_positions,
    veto_if_risk_rejects,
)

log = setup_logging()


@dataclass
class Decision:
    symbol: str
    action: str  # BUY/SELL/HOLD/WATCH/NO_TRADE
    score: float
    confidence: float
    position_size: float
    reason: str
    regime: dict


class DecisionEngine:
    """
    Recomendaciones de papel (BUY/SELL/WATCH/NO_TRADE) con filtro de régimen,
    tamaño por volatilidad y vetos de riesgo. No envía órdenes al broker.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.journal = get_journal_engine(settings.data.journal_db)

    def generate(self, prices: Dict[str, pd.DataFrame]) -> List[Decision]:
        feats = build_features(prices)
        regime = detect_regime(
            self.settings.universe, self.settings.engine, self.settings.data, prices
        )
        sma = SMACrossover(
            fast_window=int(self.settings.strategy.params.get("fast_window", 10)),
            slow_window=int(self.settings.strategy.params.get("slow_window", 30)),
        )
        mr = MeanReversion(window=20, num_std=2.0)
        sma_sig = sma.generate_signals(prices)
        mr_sig = mr.generate_signals(prices)
        combined = {sym: {"sma": sma_sig.get(sym), "mr": mr_sig.get(sym)} for sym in prices.keys()}
        weights = EnsembleWeights(strategy_weights={"sma": 0.6, "mr": 0.4})
        scores = score_strategies(combined, weights)
        scores = apply_regime_filter(scores, regime)

        risk = RiskManager(self.settings.risk)
        killswitch = risk.killswitch_active()
        vol_w = volatility_target_weights(
            prices, target_annual_vol=float(self.settings.risk.target_vol_annual)
        )
        direction = self.settings.trading.direction

        staged: list[dict] = []
        actions: dict[str, str] = {}
        for sym, df in prices.items():
            series = scores.get(sym)
            data_ok = (
                isinstance(df, pd.DataFrame)
                and not df.empty
                and "close" in df.columns
                and series is not None
                and not series.empty
            )
            score = float(series.iloc[-1]) if data_ok and series is not None else float("nan")
            allowed, _msg = risk.check_symbol_allowed(sym)
            action, reason = classify_paper_action(
                score=score,
                direction=direction,
                killswitch=killswitch,
                symbol_allowed=allowed,
                data_ok=data_ok,
            )
            desired_sign = 0
            effective_sign = 0
            if data_ok and series is not None:
                pos_series = score_to_position(series)
                desired_sign = int(pos_series.iloc[-1]) if not pos_series.empty else 0
                atr_s = feats.get(sym, {}).get("atr_14")
                if isinstance(atr_s, pd.Series) and not atr_s.empty:
                    effective = enforce_stops(pos_series, df["close"].astype(float), atr_s)
                    effective_sign = int(effective.iloc[-1])
                else:
                    effective_sign = desired_sign
                action, veto_reason = apply_stop_veto(action, desired_sign, effective_sign)
                if veto_reason:
                    reason = veto_reason
            if action in {"BUY", "SELL"}:
                last_price = (
                    float(df["close"].iloc[-1])
                    if data_ok and isinstance(df, pd.DataFrame) and not df.empty
                    else 100.0
                )
                action, risk_veto = veto_if_risk_rejects(
                    action,
                    risk,
                    symbol=sym,
                    price=last_price,
                )
                if risk_veto:
                    reason = risk_veto
            actions[sym] = action
            staged.append(
                {
                    "symbol": sym,
                    "action": action,
                    "score": score,
                    "reason": reason,
                }
            )

        sizes = size_paper_positions(
            actions,
            vol_w,
            max_position_pct=float(self.settings.risk.max_position_pct),
            max_total_exposure_pct=float(self.settings.risk.max_total_exposure_pct),
        )
        decisions: List[Decision] = []
        for row in staged:
            sym = str(row["symbol"])
            score = float(row["score"])
            action = str(row["action"])
            size = float(sizes.get(sym, 0.0))
            if action not in {"BUY", "SELL"}:
                size = 0.0
            confidence = 0.0 if not math.isfinite(score) else float(min(0.9, abs(score)))
            regime_dict = {
                "risk_on": int(regime["risk_on"].iloc[-1]) if not regime.empty else 0,
                "breadth": float(regime["breadth"].iloc[-1]) if not regime.empty else 0.0,
                "trend": int(regime["trend"].iloc[-1]) if not regime.empty else 0,
            }
            dec = Decision(
                symbol=sym,
                action=action,
                score=0.0 if not math.isfinite(score) else score,
                confidence=confidence,
                position_size=size,
                reason=str(row["reason"]),
                regime=regime_dict,
            )
            decisions.append(dec)
            try:
                from ..ops.journal import record_decision

                record_decision(
                    self.journal,
                    symbol=dec.symbol,
                    action=dec.action,
                    score=dec.score,
                    confidence=dec.confidence,
                    position_size=dec.position_size,
                    reason=dec.reason,
                    regime_json=json.dumps(dec.regime),
                    source_json=json.dumps(
                        {
                            "features": "technical (SMA/EMA/ATR/RSI/breadth)",
                            "regime_method": "VIX<MA50 + breadth + trend proxy",
                            "methodology": "paper_policy v1; no broker orders",
                        }
                    ),
                )
            except Exception as e:
                log.error("journal_write_failed %s", str(e))
        return decisions
