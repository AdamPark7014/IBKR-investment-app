from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiskConfig(BaseModel):
    max_position_pct: float = Field(100.0, description="Max position size as % of equity")
    max_total_exposure_pct: float = Field(100.0, description="Max total gross exposure %")
    daily_loss_limit_pct: float = Field(
        5.0, description="If daily PnL < -limit% of starting equity, halt"
    )
    target_vol_annual: float = Field(0.10, description="Volatility target for sizing (annualized)")
    risk_on_threshold: float = Field(0.5, description="Minimum risk-on probability to allow trades")
    max_orders_per_day: int = 50
    allowed_symbols: List[str] = Field(default_factory=list)
    killswitch_file: str = "./data/KILL_SWITCH"


class CommissionConfig(BaseModel):
    model: Literal["fixed", "tiered"] = "fixed"
    per_share: float = 0.005
    min_per_order: float = 1.0
    percent_of_value: float = 0.0  # optional ad-valorem


class SlippageConfig(BaseModel):
    bps: float = 1.0  # basis points per trade (round-trip ~2*bps)
    ticks: float = 0.0


class DataConfig(BaseModel):
    data_dir: str = "./data"
    cache_dir: str = "./data/cache"
    reports_dir: str = "./reports"
    journal_db: str = "./data/journal.sqlite"
    providers: List[str] = Field(default_factory=lambda: ["yahoo", "stooq"])
    max_cache_age_days: int = 7


class IBConfig(BaseModel):
    host: str = "127.0.0.1"
    paper_port: int = 4002
    live_port: int = 4001
    client_id: int = 123
    expected_account: Optional[str] = None


class UniverseConfig(BaseModel):
    symbols: List[str] = Field(default_factory=lambda: ["SPY"])
    benchmark: str = "SPY"


class EngineConfig(BaseModel):
    bar_size: str = "1d"
    history_days: int = 365 * 5
    use_cache: bool = True


class TradingConfig(BaseModel):
    allow_short: bool = False
    rebalance_band_pct: float = 0.0
    direction: Literal["long_only", "short_only", "long_short"] = "long_only"
    benefit_bps: float = 0.0
    risk_cost_bps: float = 0.0


class StrategyConfig(BaseModel):
    name: str = "sma_crossover"
    params: dict = Field(default_factory=lambda: {"fast_window": 10, "slow_window": 30})


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    mode: Literal["PAPER", "LIVE"] = "PAPER"
    live_trading_confirmed: str = Field(default="no", validation_alias="LIVE_TRADING_CONFIRMED")

    ib: IBConfig = Field(default_factory=lambda: IBConfig())
    risk: RiskConfig = Field(default_factory=lambda: RiskConfig())  # type: ignore[call-arg]
    commission: CommissionConfig = Field(default_factory=lambda: CommissionConfig())
    slippage: SlippageConfig = Field(default_factory=lambda: SlippageConfig())
    data: DataConfig = Field(default_factory=lambda: DataConfig())
    universe: UniverseConfig = Field(default_factory=lambda: UniverseConfig())
    engine: EngineConfig = Field(default_factory=lambda: EngineConfig())
    strategy: StrategyConfig = Field(default_factory=lambda: StrategyConfig())
    trading: TradingConfig = Field(default_factory=lambda: TradingConfig())

    @field_validator("live_trading_confirmed")
    @classmethod
    def normalize_confirmed(cls, v: str) -> str:
        return str(v).strip().lower()

    def resolve_paths(self) -> None:
        # Ensure directories exist
        for path in [
            Path(self.data.data_dir),
            Path(self.data.cache_dir),
            Path(self.data.reports_dir),
            Path(os.path.dirname(self.data.journal_db) or "."),
        ]:
            Path(path).mkdir(parents=True, exist_ok=True)

    def ib_port(self) -> int:
        return self.ib.live_port if self.mode.upper() == "LIVE" else self.ib.paper_port

    def live_safety_ok(self) -> tuple[bool, str]:
        if self.mode.upper() != "LIVE":
            return False, "Modo LIVE no habilitado (estás en PAPER)."
        if self.live_trading_confirmed not in {"yes", "true", "1"}:
            return False, "LIVE requiere LIVE_TRADING_CONFIRMED=yes en el entorno."
        if self.ib_port() != self.ib.live_port:
            return (
                False,
                f"El puerto activo {self.ib_port()} no es el de LIVE ({self.ib.live_port}).",
            )
        return True, "Checks de LIVE aprobados."

