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
    current_date: str | None = None


class RiskManager:
    def __init__(self, cfg: RiskConfig, state: RiskState | None = None) -> None:
        self.cfg = cfg
        self.state = state or RiskState(starting_equity_today=0.0)

    def on_new_day(self, date_str: str, starting_equity: float) -> None:
        if self.state.current_date != date_str:
            self.state.current_date = date_str
            self.state.starting_equity_today = float(starting_equity)
            self.state.orders_today = 0
            # Do not auto-clear halted; daily halt applies only to this day
            self.state.halted = False

    def check_killswitch(self) -> Tuple[bool, str]:
        if os.path.exists(self.cfg.killswitch_file):
            return False, "Kill switch activado."
        return True, "OK"

    def check_symbol_allowed(self, symbol: str) -> Tuple[bool, str]:
        if self.cfg.allowed_symbols and symbol not in self.cfg.allowed_symbols:
            return False, f"Símbolo no permitido: {symbol}"
        return True, "OK"

    def check_position_size(self, equity: float, price: float, resulting_position_qty: int) -> Tuple[bool, str]:
        notional = abs(resulting_position_qty) * price
        if notional > equity * (self.cfg.max_position_pct / 100.0):
            return False, "Tamaño de posición excede el máximo permitido."
        return True, "OK"

    def check_total_exposure(
        self, equity: float, current_positions_value: float, is_risk_reducing: bool
    ) -> Tuple[bool, str]:
        # Never block risk-reducing/orders de-risking exposure
        if is_risk_reducing:
            return True, "OK"
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
        current_position_qty: int,
    ) -> Tuple[bool, str]:
        # Allow risk-reducing orders even if halted
        is_reducing = (current_position_qty > 0 and quantity < 0) or (current_position_qty < 0 and quantity > 0)
        if self.state.halted and not is_reducing:
            return False, "Trading detenido por riesgo."
        ok, msg = self.check_daily_loss(equity)
        if not ok:
            # Daily loss triggered; still allow reducing
            if not is_reducing:
                return ok, msg
        for check in [
            self.check_killswitch,
            lambda: self.check_symbol_allowed(symbol),
            # Do not block risk-reducing orders on position-size
            (lambda: (True, "OK"))
            if is_reducing
            else (lambda: self.check_position_size(equity, price, current_position_qty + quantity)),
            lambda: self.check_total_exposure(
                equity,
                current_positions_value,
                is_risk_reducing=is_reducing,
            ),
            self.check_order_count,
        ]:
            ok, msg = check()
            if not ok:
                return ok, msg
        return True, "OK"

    def notify_order_sent(self) -> None:
        self.state.orders_today += 1

