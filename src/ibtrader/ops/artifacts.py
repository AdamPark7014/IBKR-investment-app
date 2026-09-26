from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from ..backtest.engine import BacktestResult
from ..backtest.reasons import TradeReason
from ..config import AppSettings


def _coerce_reason(value: object) -> str:
    return TradeReason.coerce(value)


def _json_safe(obj: Any) -> Any:
    """Recursively convert NaN/Inf floats to None for JSON null emission."""
    import math

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _hash_series(s: pd.Series) -> str:
    h = hashlib.sha256()
    # Use ISO date + value
    for idx, val in s.dropna().items():
        h.update(str(pd.Timestamp(idx)).encode("utf-8"))
        h.update(str(float(val)).encode("utf-8"))
    return h.hexdigest()


def dataset_hash(data: Dict[str, pd.DataFrame]) -> str:
    h = hashlib.sha256()
    for sym in sorted(data.keys()):
        df = data[sym]
        h.update(sym.encode("utf-8"))
        # Hash all standard OHLCV columns if present, else all columns
        cols = [
            c
            for c in ["open", "high", "low", "close", "adj_close", "volume"]
            if c in df.columns
        ] or list(df.columns)
        for c in cols:
            h.update(c.encode("utf-8"))
            h.update(_hash_series(df[c].astype(float)).encode("utf-8"))
        h.update(str(len(df)).encode("utf-8"))
        if len(df) > 0:
            h.update(str(df.index.min()).encode("utf-8"))
            h.update(str(df.index.max()).encode("utf-8"))
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        return out
    except Exception:
        return "unknown"


def config_hash(settings: AppSettings) -> str:
    # Stable JSON of key configuration
    blob = json.dumps(
        {
            "mode": settings.mode,
            "risk": settings.risk.model_dump(),
            "commission": settings.commission.model_dump(),
            "slippage": settings.slippage.model_dump(),
            "trading": settings.trading.model_dump(),
            "strategy": settings.strategy.model_dump(),
            "engine": settings.engine.model_dump(),
            "universe": settings.universe.model_dump(),
            "data": {"providers": settings.data.providers},
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def save_run_artifact(
    result: BacktestResult,
    settings: AppSettings,
    data: Dict[str, pd.DataFrame],
    out_dir: str,
    exp_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ds_hash = dataset_hash(data)
    sym_dates = {
        k: {
            "start": str(v.index.min()),
            "end": str(v.index.max()),
            "rows": int(len(v)),
        }
        for k, v in data.items()
    }
    art = {
        "run_id": exp_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "config_hash": config_hash(settings),
        "dataset": {"hash": ds_hash, "symbols": sym_dates},
        "strategy": settings.strategy.model_dump(),
        "strategy_version": (
            f"{settings.strategy.name}-"
            f"{settings.strategy.params.get('fast_window','')}-"
            f"{settings.strategy.params.get('slow_window','')}-"
            f"{git_commit()[:7]}-"
            f"{_pkg_version('ibtrader')}"
        ),
        "commission": settings.commission.model_dump(),
        "slippage": settings.slippage.model_dump(),
        "execution": {"model": "next_open_with_slippage"},
        "seeds": {"gmm": 42},
        "metrics": {
            "cagr": result.stats.cagr,
            "sharpe": result.stats.sharpe,
            "sortino": result.stats.sortino,
            "calmar": result.stats.calmar,
            "recovery_factor": result.stats.recovery_factor,
            "max_dd": result.stats.max_drawdown,
            "win_rate": result.stats.win_rate,
            "total_return": result.stats.total_return,
            "volatility": result.stats.volatility,
            "trade_count": result.stats.trade_count,
            "total_commission": result.stats.total_commission,
            "turnover": result.stats.turnover,
            "win_rate_trades": result.stats.win_rate_trades,
            "profit_factor": result.stats.profit_factor,
            "expectancy": result.stats.expectancy,
            "var_95": result.stats.var_95,
            "cvar_95": result.stats.cvar_95,
            "current_underwater_days": result.stats.current_underwater_days,
            "max_underwater_days": result.stats.max_underwater_days,
        },
        "trades": [
            {
                "date": d,
                "symbol": s,
                "qty": int(q),
                "price": float(p),
                # Dual keys for compatibility: reason (legacy) + exit_reason (spec §10)
                "reason": _coerce_reason(reason),
                "exit_reason": _coerce_reason(reason),
            }
            for d, s, q, p, reason in result.trades
        ],
        "trades_by_reason": (
            lambda items: {k: int(v) for k, v in items}
        )(
            __import__("collections").Counter(
                [_coerce_reason(r) for *_, r in result.trades]
            ).items()
        ),
        # Equity curve as pairs for reproducibility
        "equity_curve": [[str(idx), float(val)] for idx, val in result.equity_curve.items()],
    }
    if extra:
        # Allow override of strategy_version when a procedure (e.g., walk-forward) chose different params
        override = extra.get("strategy_version_override") if isinstance(extra, dict) else None
        if override:
            art["strategy_version"] = f"{override}-{git_commit()[:7]}-{_pkg_version('ibtrader')}"
        art["extra"] = extra
    out_path = os.path.join(out_dir, f"artifact_{exp_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        # Convert NaN/Inf to null so flat-equity undefined ratios are honest
        json.dump(_json_safe(art), f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return out_path

