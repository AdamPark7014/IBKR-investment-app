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
    @abc.abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """
        Return per-symbol signal series in [-1, 0, 1] where:
        -1 = short, 0 = flat, 1 = long. Backtest engine will convert to positions.
        Index must align with input data indexes (dates).
        """
        ...

