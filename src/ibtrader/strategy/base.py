from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict

import pandas as pd


@dataclass
class StrategyContext:
    # Placeholder for future extensions (account info, constraints)
    pass


class Strategy(abc.ABC):
    #: How the backtest engine reads the series returned by ``generate_signals``.
    #:
    #: * ``"direction"`` (default): each value is a sign in ``[-1, 0, 1]``; the engine
    #:   sizes the position itself (equal weight across active symbols, optional
    #:   volatility targeting) and trades on sign changes.
    #: * ``"weight"``: each value is a signed target weight (fraction of NAV) that is
    #:   already sized and buffered upstream (``pipeline/system.py``). The engine only
    #:   enforces direction, the regime veto and the risk manager, and trades when the
    #:   weight differs from the last executed one. Gross exposure is capped by
    #:   ``RiskConfig.max_total_exposure_pct``.
    signal_kind: str = "direction"

    @abc.abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """
        Return per-symbol signal series in [-1, 0, 1] where:
        -1 = short, 0 = flat, 1 = long. Backtest engine will convert to positions.
        Index must align with input data indexes (dates).

        When ``signal_kind == "weight"`` the series are signed target weights
        (fraction of NAV) instead of signs; see ``signal_kind``.
        """
        ...
