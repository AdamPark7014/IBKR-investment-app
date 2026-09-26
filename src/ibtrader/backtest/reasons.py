from __future__ import annotations

from enum import Enum


class TradeReason(str, Enum):
    """Centralized fill/exit reason codes for trade records.

    Every engine fill must use one of these values. Arbitrary free-form
    strings are not permitted in production paths.
    """

    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    KILL_SWITCH = "kill_switch"
    FLIP_CLOSE_ONLY = "flip_close_only"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    EMERGENCY = "emergency"
    END_OF_BACKTEST = "end_of_backtest"

    @classmethod
    def coerce(cls, value: object) -> str:
        if isinstance(value, cls):
            return value.value
        if isinstance(value, str):
            try:
                return cls(value).value
            except ValueError:
                return cls.SIGNAL.value
        return cls.SIGNAL.value
