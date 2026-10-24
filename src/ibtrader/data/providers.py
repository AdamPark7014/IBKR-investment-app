from __future__ import annotations

import abc
import logging
import os
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import requests
import yfinance as yf
from ib_async import IB, Stock

from .lineage import DataFrameWithMeta, DataLineage
from .validators import validate_timeseries_strict

log = logging.getLogger("ibtrader.data.providers")


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
        # Ensure business-day index only (drop non-business days)
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)
        df = df[df.index.dayofweek < 5]
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
        # yfinance 1.x returns (field, ticker); keep the field level only.
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
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


def apply_total_return_adjustment(df: pd.DataFrame) -> pd.DataFrame:
    """Scale OHLC by ``adj_close / close`` so prices include dividends and splits (total return).

    Yahoo's raw ``close`` drops on every ex-dividend date (PDBC lost 26.6 % on 2021-12-03 from a
    USD 5.39 distribution); a long-only ETF backtest on raw closes loses every dividend and sees
    spurious crashes. The unadjusted close is kept as ``close_raw`` (same convention as Tiingo).
    Rows without a usable factor keep their raw values.
    """
    if "adj_close" not in df.columns or "close" not in df.columns:
        return df
    out = df.copy()
    close = out["close"].astype(float)
    adj = out["adj_close"].astype(float)
    factor = (adj / close).where((close > 0) & adj.notna() & close.notna(), 1.0)
    out["close_raw"] = close
    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = out[col].astype(float) * factor
    out["adj_close"] = out["close"]
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
        out = apply_total_return_adjustment(_normalize_df_ohlcv(df))
        ok, msg = validate_timeseries_strict(out)
        if not ok:
            raise RuntimeError(f"Data inválida de Yahoo: {msg}")
        lin = DataLineage(
            source="yahoo",
            source_url=f"https://finance.yahoo.com/quote/{symbol}",
            methodology="yfinance daily bars; OHLC scaled by Adj Close/Close (total return), close_raw unadjusted",
            parameters={"interval": "1d", "auto_adjust": False, "total_return_adjusted": True},
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
            except Exception as e:  # cleanup only: never hides the real error, but it is not silent either
                log.warning("ibkr_disconnect_failed reason=%s", e)


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
        reasons: List[str] = []
        for url in urls:
            try:
                resp = requests.get(url, timeout=20, headers=headers, allow_redirects=True)
            except requests.RequestException as e:
                reasons.append(f"{url}: {type(e).__name__}: {e}")
                continue
            if resp.status_code != 200:
                reasons.append(f"{url}: HTTP {resp.status_code}")
                continue
            if not resp.text or "Date,Open,High,Low,Close,Volume" not in resp.text:
                reasons.append(f"{url}: respuesta sin cabecera CSV ({(resp.text or '')[:60]!r})")
                continue
            csv_text = resp.text
            break
        if not csv_text:
            raise RuntimeError("Stooq CSV no disponible: " + "; ".join(reasons))
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


@dataclass(frozen=True)
class SymbolMetadata:
    """Listing metadata from a provider; the basis for delistings in the lifecycle universe."""

    symbol: str
    name: Optional[str] = None
    start_date: Optional[str] = None  # first available bar (ISO date)
    end_date: Optional[str] = None  # last available bar (ISO date); far from today => delisted or halted
    exchange: Optional[str] = None
    description: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


class TiingoProvider(MarketDataProvider):
    """Tiingo end-of-day prices (https://www.tiingo.com/documentation/end-of-day).

    Why Tiingo (playbook annex 5, 21-10-2026): 30+ years of EOD history, split/dividend adjusted *and* raw
    close in the same payload, metadata with ``startDate``/``endDate`` per ticker (delistings), Starter tier
    free (500 symbols/month, 50 requests/hour, 1,000/day), Power $30/month.

    Columns returned (same schema as ``_normalize_df_ohlcv``): ``open/high/low/close/volume`` are the
    *adjusted* series (``adjOpen``…``adjVolume``), ``adj_close`` duplicates ``close`` for callers that look
    for it, ``close_raw`` is the unadjusted close, ``div_cash`` / ``split_factor`` are kept when present.
    """

    BASE_URL = "https://api.tiingo.com/tiingo/daily"
    _ADJ_MAP = {
        "adjOpen": "open",
        "adjHigh": "high",
        "adjLow": "low",
        "adjClose": "close",
        "adjVolume": "volume",
    }
    _RAW_FALLBACK = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}

    def __init__(
        self,
        token: str,
        *,
        max_retries: int = 3,
        backoff_s: float = 2.0,
        max_backoff_s: float = 60.0,
        timeout_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token or not str(token).strip():
            raise ValueError("token Tiingo inválido o ausente (DATA__TIINGO_TOKEN)")
        self._token = str(token).strip()
        self.max_retries = int(max_retries)
        self.backoff_s = float(backoff_s)
        self.max_backoff_s = float(max_backoff_s)
        self.timeout_s = float(timeout_s)
        self._sleep = sleep

    # ---- HTTP -------------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "User-Agent": "ibtrader/0.1 (+paper-first)"}

    def _get_json(self, url: str, params: Dict[str, Any], what: str) -> Any:
        """GET with the Starter-tier etiquette: 429 => exponential backoff, up to ``max_retries`` retries."""
        attempt = 0
        while True:
            query = {**params, "token": self._token}
            try:
                resp = requests.get(url, params=query, headers=self._headers(), timeout=self.timeout_s)
            except requests.RequestException as e:
                raise RuntimeError(f"Tiingo {what}: error de red {type(e).__name__}: {e}") from e
            status = int(resp.status_code)
            if status == 200:
                try:
                    return resp.json()
                except ValueError as e:
                    raise RuntimeError(f"Tiingo {what}: respuesta no es JSON ({(resp.text or '')[:120]!r})") from e
            if status in (401, 403):
                raise RuntimeError(f"token Tiingo inválido o ausente (HTTP {status} en {what})")
            if status == 404:
                raise RuntimeError(f"Tiingo {what}: símbolo desconocido (HTTP 404)")
            if status == 429:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Tiingo {what}: límite de tasa (HTTP 429) tras {attempt} reintentos; "
                        "tier Starter = 50 req/hora, 1.000/día, 500 símbolos/mes"
                    )
                wait = self._retry_wait(resp, attempt)
                log.warning("tiingo_rate_limited what=%s attempt=%s wait_s=%.1f", what, attempt + 1, wait)
                self._sleep(wait)
                attempt += 1
                continue
            raise RuntimeError(f"Tiingo {what}: HTTP {status}: {(resp.text or '')[:200]!r}")

    def _retry_wait(self, resp: Any, attempt: int) -> float:
        header = None
        headers = getattr(resp, "headers", None)
        if headers:
            header = headers.get("Retry-After") if hasattr(headers, "get") else None
        if header:
            try:
                return min(max(float(header), 0.0), self.max_backoff_s)
            except ValueError:
                pass
        return min(self.backoff_s * (2**attempt), self.max_backoff_s)

    # ---- API --------------------------------------------------------------------------
    def fetch_metadata(self, symbol: str) -> SymbolMetadata:
        """``GET /tiingo/daily/{ticker}``: name, exchange and first/last available dates (delisting basis)."""
        url = f"{self.BASE_URL}/{symbol.upper()}"
        raw = self._get_json(url, {}, what=f"metadata {symbol}")
        if not isinstance(raw, dict):
            raise RuntimeError(f"Tiingo metadata {symbol}: respuesta inesperada {type(raw).__name__}")

        def _d(key: str) -> Optional[str]:
            v = raw.get(key)
            if not v:
                return None
            return str(pd.Timestamp(v).date())

        return SymbolMetadata(
            symbol=str(raw.get("ticker") or symbol).upper(),
            name=raw.get("name"),
            start_date=_d("startDate"),
            end_date=_d("endDate"),
            exchange=raw.get("exchangeCode"),
            description=raw.get("description"),
            raw=dict(raw),
        )

    def fetch_daily_ohlcv(
        self, symbol: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> DataFrameWithMeta:
        url = f"{self.BASE_URL}/{symbol.upper()}/prices"
        params: Dict[str, Any] = {"format": "json"}
        if start:
            params["startDate"] = start
        if end:
            params["endDate"] = end
        rows = self._get_json(url, params, what=f"prices {symbol}")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"Tiingo vacío para {symbol} (start={start}, end={end})")
        raw = pd.DataFrame(rows)
        if "date" not in raw.columns:
            raise RuntimeError(f"Tiingo {symbol}: payload sin columna 'date' ({list(raw.columns)[:8]})")
        out = self._to_ohlcv(raw, symbol)
        ok, msg = validate_timeseries_strict(out)
        if not ok:
            raise RuntimeError(f"Data inválida de Tiingo ({symbol}): {msg}")
        lin = DataLineage(
            source="tiingo",
            source_url=url,
            methodology="Tiingo EOD adjusted bars (adjOpen/adjHigh/adjLow/adjClose/adjVolume) + close_raw",
            parameters={"interval": "1d", "start": start, "end": end, "adjusted": True},
            license="Tiingo TOS (personal/non-commercial on Starter; Commercial plan for redistribution)",
        )
        return DataFrameWithMeta(out, lin)

    def _to_ohlcv(self, raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
        has_adj = all(k in raw.columns for k in self._ADJ_MAP)
        mapping = self._ADJ_MAP if has_adj else self._RAW_FALLBACK
        if not has_adj:
            missing = [k for k in self._RAW_FALLBACK if k not in raw.columns]
            if missing:
                raise RuntimeError(f"Tiingo {symbol}: faltan columnas {missing} en el payload")
            log.warning("tiingo_sin_ajustados symbol=%s usando open/high/low/close/volume crudos", symbol)
        # Plain arrays, not Series: a Series would be re-aligned against the DatetimeIndex below and go NaN.
        def _col(name: str) -> Any:
            return pd.to_numeric(raw[name], errors="coerce").astype(float).to_numpy()

        data: Dict[str, Any] = {dst: _col(src) for src, dst in mapping.items()}
        data["adj_close"] = data["close"]
        if "close" in raw.columns:
            data["close_raw"] = _col("close")
        if "divCash" in raw.columns:
            data["div_cash"] = _col("divCash")
        if "splitFactor" in raw.columns:
            data["split_factor"] = _col("splitFactor")
        idx = pd.to_datetime(raw["date"], utc=True).dt.tz_localize(None).dt.normalize()
        out = pd.DataFrame(data, index=pd.DatetimeIndex(idx.to_numpy(), name="date")).sort_index()
        return out


@dataclass
class DataQualityGate:
    min_rows: int = 252

    def validate(self, data: DataFrameWithMeta) -> None:
        ok, msg = validate_timeseries_strict(data.data)
        if not ok:
            details = msg
            required = [c for c in ["open", "high", "low", "close", "volume"] if c in data.data.columns]
            if "faltantes" in msg.lower() and required:
                mask = data.data[required].isna().any(axis=1)
                bad_idx = [str(ts) for ts in list(data.data.index[mask])[:10]]
                details = f"{msg} Fechas con NaN: {bad_idx} Proveedor: {data.lineage.source}"
            raise RuntimeError(f"Data inválida: {details}")
        if len(data.data) < self.min_rows:
            raise RuntimeError(f"Data insuficiente: {len(data.data)} filas (<{self.min_rows})")

