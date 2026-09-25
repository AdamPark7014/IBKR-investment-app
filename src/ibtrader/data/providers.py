from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from io import StringIO
from typing import Optional

import pandas as pd
import requests
import yfinance as yf
from ib_async import IB, Stock

from .lineage import DataFrameWithMeta, DataLineage
from .validators import validate_timeseries_strict


class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    def fetch_daily_ohlcv(
        self, symbol: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> DataFrameWithMeta:
        ...

class FixtureProvider(MarketDataProvider):
    """
    Test/CI-only provider that loads deterministic local fixtures.
    Path resolution:
      - ENV DATA__FIXTURE_DIR, else ./tests/fixtures
      - File pattern: <symbol>_1d.csv or <symbol>_1d.parquet
    """
    def __init__(self, directory: Optional[str] = None) -> None:
        self.dir = directory or os.environ.get("DATA__FIXTURE_DIR", "./tests/fixtures")

    def fetch_daily_ohlcv(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> DataFrameWithMeta:
        base = os.path.join(self.dir, f"{symbol.upper()}_1d")
        df: Optional[pd.DataFrame] = None
        for ext in ("parquet", "csv"):
            path = f"{base}.{ext}"
            if os.path.exists(path):
                if ext == "parquet":
                    df = pd.read_parquet(path)
                else:
                    tmp = pd.read_csv(path)
                    if "date" in tmp.columns:
                        tmp["date"] = pd.to_datetime(tmp["date"])
                        tmp = tmp.set_index("date")
                    df = tmp
                break
        if df is None or df.empty:
            raise RuntimeError(f"Fixture no encontrado para {symbol} en {self.dir}")
        # Ensure business-day index with at least 260 rows by forward-filling
        last = pd.to_datetime(df.index.max())
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)
        # Reindex to business days from the first to last date
        bidx = pd.bdate_range(start=pd.to_datetime(df.index.min()), end=last)
        df = df.reindex(bidx).ffill()
        if len(df) < 260:
            # Extend backwards to reach 260 rows total
            need = 260 - len(df)
            ext_idx = pd.bdate_range(end=bidx.min() - pd.Timedelta(days=1), periods=need)
            df = pd.concat([df.reindex(ext_idx).ffill(), df])
        ok, msg = validate_timeseries_strict(df)
        if not ok:
            raise RuntimeError(f"Fixture inválido: {msg}")
        lin = DataLineage(
            source="fixture",
            source_url=None,
            methodology="local CSV/Parquet fixture",
            parameters={"file": os.path.basename(path)},
            license="internal-test-only",
        )
        return DataFrameWithMeta(df, lin)


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


class IBKRProvider(MarketDataProvider):
    def __init__(self, host: str = "127.0.0.1", port: int = 4002, client_id: int = 123) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id

    def fetch_daily_ohlcv(
        self, symbol: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> DataFrameWithMeta:
        ib = IB()
        try:
            ib.connect(self.host, self.port, clientId=self.client_id, readonly=True, timeout=5)
            contract = Stock(symbol, "SMART", "USD")
            # 5 years daily bars as a default
            bars = ib.reqHistoricalData(
                contract,
                endDateTime=end or "",
                durationStr="5 Y",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
            )
            if not bars:
                raise RuntimeError("IBKR vacío")
            # Convert list of BarData-like to DataFrame
            rows = []
            for b in bars:
                rows.append(
                    {
                        "date": pd.to_datetime(getattr(b, "date")),
                        "open": float(getattr(b, "open")),
                        "high": float(getattr(b, "high")),
                        "low": float(getattr(b, "low")),
                        "close": float(getattr(b, "close")),
                        "volume": float(getattr(b, "volume")),
                    }
                )
            df = pd.DataFrame(rows).set_index("date").sort_index()
            ok, msg = validate_timeseries_strict(df)
            if not ok:
                raise RuntimeError(f"Data inválida de IBKR: {msg}")
            lin = DataLineage(
                source="ibkr",
                source_url="ib_async historical",
                methodology="IBKR TRADES daily bars",
                parameters={"end": end, "durationStr": "5 Y"},
                license="IBKR data (account subscriptions apply)",
            )
            return DataFrameWithMeta(df, lin)
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass


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

