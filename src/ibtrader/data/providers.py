from __future__ import annotations

import abc
from dataclasses import dataclass
from io import StringIO
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

from .lineage import DataFrameWithMeta, DataLineage
from .validators import validate_timeseries_strict


class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    def fetch_daily_ohlcv(
        self, symbol: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> DataFrameWithMeta:
        ...


def _normalize_df_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.copy()
            df.columns = df.columns.get_level_values(0)
        except Exception:
            pass
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


class YahooProvider(MarketDataProvider):
    def fetch_daily_ohlcv(
        self, symbol: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> DataFrameWithMeta:
        df = yf.download(
            symbol,
            start=start,
            end=end,
            interval="1d",
            group_by="column",
            auto_adjust=False,
            progress=False,
            actions=False,
            threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError("yfinance vacío")
        out = _normalize_df_ohlcv(df)
        ok, msg = validate_timeseries_strict(out)
        if not ok:
            raise RuntimeError(f"Data inválida de Yahoo: {msg}")
        lin = DataLineage(
            source="yahoo",
            source_url=f"https://finance.yahoo.com/quote/{symbol}",
            methodology="yfinance daily bars",
            parameters={"interval": "1d", "auto_adjust": False},
            license="Yahoo TOS (research use)",
        )
        return DataFrameWithMeta(out, lin)


class StooqProvider(MarketDataProvider):
    def fetch_daily_ohlcv(
        self, symbol: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> DataFrameWithMeta:
        tkr = symbol.lstrip("^").lower() + ".us"
        urls = [
            f"https://stooq.com/q/d/l/?s={tkr}&i=d",
            f"https://stooq.pl/q/d/l/?s={tkr}&i=d",
        ]
        headers = {
            "User-Agent": "curl/8.4.0",
            "Accept": "text/csv, */*;q=0.1",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
        csv_text: Optional[str] = None
        for url in urls:
            try:
                resp = requests.get(url, timeout=20, headers=headers, allow_redirects=True)
                if (
                    resp.status_code == 200
                    and resp.text
                    and "Date,Open,High,Low,Close,Volume" in resp.text
                ):
                    csv_text = resp.text
                    break
            except Exception:
                continue
        if not csv_text:
            raise RuntimeError("Stooq CSV no disponible")
        df = pd.read_csv(StringIO(csv_text))
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
        ok, msg = validate_timeseries_strict(out)
        if not ok:
            raise RuntimeError(f"Data inválida de Stooq: {msg}")
        lin = DataLineage(
            source="stooq",
            source_url="https://stooq.com",
            methodology="daily CSV endpoint",
            parameters={"interval": "1d"},
            license="Stooq TOS (research use)",
        )
        return DataFrameWithMeta(out, lin)


@dataclass
class DataQualityGate:
    min_rows: int = 252

    def validate(self, data: DataFrameWithMeta) -> None:
        ok, msg = validate_timeseries_strict(data.data)
        if not ok:
            raise RuntimeError(f"Data inválida: {msg}")
        if len(data.data) < self.min_rows:
            raise RuntimeError(f"Data insuficiente: {len(data.data)} filas (<{self.min_rows})")

