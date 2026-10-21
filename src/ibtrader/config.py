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
    cumulative_loss_limit_pct: float = Field(
        20.0, description="If cumulative PnL < -limit% vs first equity, restrict (blocks new entries)"
    )
    drawdown_limit_pct: float = Field(
        20.0, description="If drawdown from peak < -limit%, restrict (blocks new entries)"
    )
    target_vol_annual: float = Field(0.10, description="Volatility target for sizing (annualized)")
    risk_on_threshold: float = Field(0.5, description="Minimum risk-on probability to allow trades")
    max_orders_per_day: int = 50
    allowed_symbols: List[str] = Field(default_factory=list)
    killswitch_file: str = "./data/KILL_SWITCH"
    stop_loss_per_position_pct: float = Field(
        0.0,
        description="Optional per-position stop loss (% from average price). 0 disables.",
    )
    emergency_flatten_on_kill: bool = Field(
        True, description="If killswitch is active, force emergency flatten at next open"
    )
    cooldown_bars: int = Field(0, description="After a forced exit, bars to wait before reopening")
    killswitch_action: Literal["flatten", "block_new_only"] = Field(
        "flatten",
        description="Kill-switch behavior: 'flatten' liquidates positions; 'block_new_only' prevents new opens only.",
    )

    @field_validator(
        "daily_loss_limit_pct",
        "cumulative_loss_limit_pct",
        "drawdown_limit_pct",
        "target_vol_annual",
        "stop_loss_per_position_pct",
    )
    @classmethod
    def _non_negative_pct(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Percent-like limits must be >= 0.")
        return v

    @field_validator(
        "daily_loss_limit_pct",
        "cumulative_loss_limit_pct",
        "drawdown_limit_pct",
        "stop_loss_per_position_pct",
    )
    @classmethod
    def _pct_le_100(cls, v: float) -> float:
        if v > 100.0:
            raise ValueError("Percent-like limits must be <= 100.")
        return v
    @field_validator("max_position_pct", "max_total_exposure_pct")
    @classmethod
    def _pos_exposure_bounds(cls, v: float) -> float:
        if v < 0.0 or v > 100.0:
            raise ValueError("max_position_pct and max_total_exposure_pct must be in [0, 100].")
        return v

    @field_validator("cooldown_bars")
    @classmethod
    def _cooldown_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("cooldown_bars must be >= 0")
        return v


class CommissionConfig(BaseModel):
    """IBKR US stocks/ETFs commission schedule (read 2026-10-21, see docs/research annex 4)."""

    model: Literal["fixed", "tiered"] = "fixed"
    # Fixed: USD 0.005/share, min USD 1.00/order, max 1 % of trade value.
    per_share: float = 0.005
    min_per_order: float = 1.0
    max_percent_of_value: float = Field(default=1.0, description="Cap as % of trade value (IBKR Fixed: 1 %)")
    percent_of_value: float = 0.0  # optional ad-valorem (legacy)
    # Tiered (<=300k shares/month): USD 0.0035/share, min USD 0.35, + exchange + clearing + pass-through.
    tiered_per_share: float = 0.0035
    tiered_min_per_order: float = 0.35
    tiered_exchange_per_share: float = Field(
        default=0.0030,
        description="Exchange fee when removing liquidity (NOT verified)",
    )
    clearing_per_share: float = 0.0002
    pass_through_pct_of_commission: float = 0.000175 + 0.00056  # NYSE + FINRA pass-through
    sanity_min_all_in_bps: float = Field(
        default=2.5,
        description="IBKR Pro clients' real all-in cost (2.5-4 bp, jul-2026); reports flag cheaper models",
    )


class RegFeesConfig(BaseModel):
    """US regulatory fees on sells (SEC Section 31, FINRA TAF, CAT). Rates as of 2026-10-21."""

    sec_fee_rate: float = Field(
        default=0.0000206,
        description="SEC fee x notional sold (USD 20.60/million, since 2026-04-04)",
    )
    finra_taf_per_share: float = Field(default=0.000195, description="FINRA TAF per share sold (normal rate)")
    finra_taf_max_per_order: float = 9.79
    finra_taf_paused_until: Optional[str] = Field(
        default="2026-12-31",
        description="ISO date; TAF is USD 0 through this date",
    )
    cat_per_share: float = 0.000003


class SlippageConfig(BaseModel):
    """Spread + impact model (annex 4): half-spread by symbol class plus square-root impact."""

    model: Literal["bps", "spread_impact"] = "spread_impact"
    bps: float = 1.0  # legacy flat slippage per trade (used when model == "bps")
    ticks: float = 0.0
    spread_bps_default: float = Field(
        default=2.0,
        description="Full quoted spread (bps) for unknown symbols; core ETFs ~0-2",
    )
    spread_bps_by_symbol: dict = Field(
        default_factory=lambda: {
            "SPY": 0.5, "IVV": 1.0, "VTI": 1.0, "QQQ": 0.7, "IWM": 0.9, "EFA": 1.5, "VEA": 2.0,
            "EEM": 1.5, "VWO": 2.0, "IEF": 1.5, "TLT": 1.0, "TIP": 3.0, "GLD": 1.0, "DBC": 5.0,
            "PDBC": 5.0, "VNQ": 2.0, "BIL": 1.0, "SGOV": 1.0,
        }
    )
    half_spread_mult: float = Field(default=1.0, description="1.0 = cross the spread; 0.5 = patient limit at mid")
    impact_y: float = Field(
        default=0.5,
        description="Y in Y*sigma_daily*sqrt(Q/ADV); Toth 'order unity', 0.5 conservative",
    )
    impact_exponent: float = 0.5
    adv_window_days: int = 20
    sigma_window_days: int = 20


class DataConfig(BaseModel):
    data_dir: str = "./data"
    cache_dir: str = "./data/cache"
    reports_dir: str = "./reports"
    journal_db: str = "./data/journal.sqlite"
    providers: List[str] = Field(default_factory=lambda: ["yahoo", "stooq"])
    max_cache_age_days: int = 7
    # Point-in-time layer (playbook phase 1): vintages + SHA-256 manifest, lifecycle universe, loud validators.
    tiingo_token: str = Field(
        default="",
        description="Tiingo API token (DATA__TIINGO_TOKEN); empty disables the provider",
    )
    vintage_dir: str = Field(default="./data/vintages", description="Parquet snapshots by vintage_date + manifest.json")
    write_manifest: bool = True
    universe_file: Optional[str] = Field(
        default=None,
        description="JSON/YAML with symbol lifecycle (listed_from, delisted_on)",
    )
    max_price_spike_pct: float = Field(
        default=25.0,
        description="Reject bars whose close jumps more than this % day over day",
    )
    reject_future_bars: bool = Field(default=True, description="Fail loud if any bar is dated after today (UTC)")


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
    allow_broker_orders: bool = False
    allow_short: bool = False
    rebalance_band_pct: float = 0.0
    direction: Literal["long_only", "short_only", "long_short"] = "long_only"
    benefit_bps: float = 0.0
    risk_cost_bps: float = 0.0


class StrategyConfig(BaseModel):
    name: str = "sma_crossover"
    params: dict = Field(default_factory=lambda: {"fast_window": 10, "slow_window": 30})


class ResearchConfig(BaseModel):
    """Research discipline (playbook phase 1): frozen hold-out and trial budget."""

    holdout_start: Optional[str] = Field(
        default=None,
        description="ISO date. Bars on/after this date are hidden from research runs unless confirmation_mode",
    )
    confirmation_mode: bool = Field(default=False, description="Open the frozen hold-out once; every opening is logged")
    max_holdout_openings: int = 1
    trial_budget_target_sharpe: float = Field(
        default=1.0, description="SR used in the trial budget: years_needed >= 2*ln(N)/SR^2 (Bailey et al. 2014)"
    )
    fail_on_budget_exceeded: bool = True


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
    reg_fees: RegFeesConfig = Field(default_factory=lambda: RegFeesConfig())
    slippage: SlippageConfig = Field(default_factory=lambda: SlippageConfig())
    research: ResearchConfig = Field(default_factory=lambda: ResearchConfig())
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
        if not (self.ib.expected_account or "").strip():
            return (
                False,
                "LIVE requiere IB_EXPECTED_ACCOUNT configurado en el entorno.",
            )
        return True, "Checks de LIVE aprobados."

