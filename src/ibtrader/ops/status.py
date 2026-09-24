from __future__ import annotations

from pathlib import Path

from ..config import AppSettings


def status_summary(settings: AppSettings) -> dict:
    mode = settings.mode
    data_dir = settings.data.data_dir
    cache_dir = settings.data.cache_dir
    reports_dir = settings.data.reports_dir
    journal_path = settings.data.journal_db
    ks = Path(settings.risk.killswitch_file).exists()
    return {
        "mode": mode,
        "ib_host": settings.ib.host,
        "ib_port": settings.ib_port(),
        "universe": settings.universe.symbols,
        "benchmark": settings.universe.benchmark,
        "data_dir": data_dir,
        "cache_dir": cache_dir,
        "reports_dir": reports_dir,
        "journal_db": journal_path,
        "kill_switch": ks,
    }

