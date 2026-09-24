from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Dict

import pandas as pd
import requests
import yfinance as yf

from ..config import DataConfig, EngineConfig, UniverseConfig
from ..logging import setup_logging
from .cache import load_from_cache, save_to_cache

log = setup_logging()


def yf_interval(bar_size: str) -> str:
    mapping = {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "60m": "60m",
        "90m": "90m",
        "1h": "60m",
        "1d": "1d",
        "1wk": "1wk",
        "1mo": "1mo",
    }
    return mapping.get(bar_size, "1d")


def normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    out.index.name = "date"
    return out


def stooq_symbol(symbol: str) -> str:
    base = symbol.lstrip("^").lower()
    return f"{base}.us"


def download_symbol_history_stooq(symbol: str) -> pd.DataFrame:
    tkr = stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={tkr}&i=d"
    resp = requests.get(url, timeout=20)
    if (
        resp.status_code != 200
        or not resp.text
        or "Date,Open,High,Low,Close,Volume" not in resp.text
    ):
        raise RuntimeError(f"Stooq no disponible para {symbol}")
    df = pd.read_csv(StringIO(resp.text))
    if df.empty:
        raise RuntimeError(f"Stooq vacío para {symbol}")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    out = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    out.index.name = "date"
    return out


def download_symbol_history(
    symbol: str, engine: EngineConfig, data_cfg: DataConfig, use_cache: bool = True
) -> pd.DataFrame:
    if use_cache:
        cached = load_from_cache(data_cfg.cache_dir, symbol, engine.bar_size)
        if cached is not None and not cached.empty:
            return cached
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=engine.history_days)
    interval = yf_interval(engine.bar_size)
    log.info(
        "download_history_start symbol=%s start=%s interval=%s",
        symbol,
        str(start_dt.date()),
        interval,
    )
    out: pd.DataFrame
    try:
        df = yf.download(
            symbol,
            start=start_dt.date(),
            end=end_dt.date(),
            interval=interval,
            auto_adjust=False,
            progress=False,
            actions=False,
            threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError("yfinance vacío")
        out = normalize_yf(df)
    except Exception:
        log.info("fallback_stooq symbol=%s", symbol)
        out = download_symbol_history_stooq(symbol)
    save_to_cache(data_cfg.cache_dir, symbol, engine.bar_size, out)
    log.info("download_history_done symbol=%s rows=%s", symbol, len(out))
    return out


def load_universe_data(
    universe: UniverseConfig, engine: EngineConfig, data_cfg: DataConfig
) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for sym in universe.symbols:
        data[sym] = download_symbol_history(sym, engine, data_cfg, use_cache=engine.use_cache)
    return data

