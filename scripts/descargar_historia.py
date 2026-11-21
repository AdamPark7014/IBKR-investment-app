"""Descarga historia diaria larga de Tiingo para investigación, sin tocar la caché de producción.

Uso (desde la raíz del repo, con el venv):  python scripts/descargar_historia.py
Lee el token de ``.env`` (``DATA__TIINGO_TOKEN``) vía ``AppSettings``; nunca lo imprime. Escribe un
parquet por símbolo en ``reports/research_data/`` (carpeta ignorada por git). Salta lo ya descargado.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ibtrader.config import AppSettings
from ibtrader.data.providers import TiingoProvider

START = "2002-01-01"
UNIVERSES = ("config/universe-10etf-historia.json", "config/universe-26etf.json", "config/universe-10etf.json")


def main() -> int:
    s = AppSettings()
    prov = TiingoProvider(s.data.tiingo_token)
    out = Path("reports/research_data")
    out.mkdir(parents=True, exist_ok=True)
    symbols: list[str] = []
    for u in UNIVERSES:
        for e in json.loads(Path(u).read_text(encoding="utf-8"))["symbols"]:
            if e["symbol"] not in symbols:
                symbols.append(e["symbol"])
    failed = []
    for sym in symbols:
        dest = out / f"{sym}_1d.parquet"
        if dest.exists():
            print(f"{sym}: ya estaba")
            continue
        try:
            df = prov.fetch_daily_ohlcv(sym, start=START).data
            df.to_parquet(dest)
            print(f"{sym}: {len(df)} barras {df.index.min().date()} -> {df.index.max().date()}")
        except Exception as exc:  # noqa: BLE001 - se informa y se sigue con el resto
            failed.append(sym)
            print(f"{sym}: ERROR {type(exc).__name__}: {str(exc)[:200]}")
        time.sleep(1.5)
    print(f"listo: {len(symbols) - len(failed)} de {len(symbols)}; fallaron: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
