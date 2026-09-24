from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

from ..config import RiskConfig


@dataclass
class RiskState:
    starting_equity_today: float
    orders_today: int = 0
    halted: bool = False


class RiskManager:
    def __init__(self, cfg: RiskConfig, state: RiskState | None = None) -> None:
        self.cfg = cfg
        self.state = state or RiskState(starting_equity_today=0.0)

    def check_killswitch(self) -> Tuple[bool, str]:
        if os.path.exists(self.cfg.killswitch_file):
            return False, "Kill switch activado."
        return True, "OK"

    def check_symbol_allowed(self, symbol: str) -> Tuple[bool, str]:
        if self.cfg.allowed_symbols and symbol not in self.cfg.allowed_symbols:
            return False, f"Símbolo no permitido: {symbol}"
        return True, "OK"

    def check_position_size(self, equity: float, price: float, quantity: int) -> Tuple[bool, str]:
        notional = abs(quantity) * price
        if notional > equity * (self.cfg.max_position_pct / 100.0):
            return False, "Tamaño de posición excede el máximo permitido."
        return True, "OK"

    def check_total_exposure(
        self, equity: float, current_positions_value: float
    ) -> Tuple[bool, str]:
        if abs(current_positions_value) > equity * (self.cfg.max_total_exposure_pct / 100.0):
            return False, "Exposición total excede el máximo permitido."
        return True, "OK"

    def check_daily_loss(self, current_equity: float) -> Tuple[bool, str]:
        limit = self.state.starting_equity_today * (self.cfg.daily_loss_limit_pct / 100.0)
        if current_equity < self.state.starting_equity_today - limit:
            self.state.halted = True
            return False, "Límite de pérdida diario excedido. Trading detenido."
        return True, "OK"

    def check_order_count(self) -> Tuple[bool, str]:
        if self.state.orders_today >= self.cfg.max_orders_per_day:
            return False, "Máximo de órdenes diarias alcanzado."
        return True, "OK"

    def approve_order(
        self,
        symbol: str,
        equity: float,
        price: float,
        quantity: int,
        current_positions_value: float,
    ) -> Tuple[bool, str]:
        if self.state.halted:
            return False, "Trading detenido por riesgo."
        for check in [
            self.check_killswitch,
            lambda: self.check_symbol_allowed(symbol),
            lambda: self.check_position_size(equity, price, quantity),
            lambda: self.check_total_exposure(equity, current_positions_value),
            self.check_order_count,
        ]:
            ok, msg = check()
            if not ok:
                return ok, msg
        return True, "OK"

    def notify_order_sent(self) -> None:
        self.state.orders_today += 1

