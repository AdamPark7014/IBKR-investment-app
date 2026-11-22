"""Respaldo diario del estado de paper: libro, curva de capital, órdenes, alertas y freeze.

Si se daña ``data/`` se pierde lo único que no se puede regenerar: qué tiene la cartera según el
sistema, la curva de capital y el historial de órdenes. Este módulo guarda un ``.zip`` por día y
conserva los últimos ``keep``.

Destino: ``IBTRADER_RESPALDO_DIR`` si está definida (conviene una carpeta sincronizada o un disco
distinto); si no, ``data/respaldos``, que protege de un archivo dañado o sobrescrito pero no de perder
el disco. Los precios (caché y vintages) y los registros de texto no entran: se regeneran.
"""

from __future__ import annotations

import os
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import AppSettings

#: Solo archivos de estado en la raíz de ``data/``. Nunca ``.env`` ni carpetas.
STATE_SUFFIXES = (".json", ".jsonl", ".sqlite")
EXCLUDE = ("vigia.lock",)
KEEP_DEFAULT = 30
PREFIX = "estado-"


def backup_dir(settings: AppSettings) -> Path:
    custom = os.environ.get("IBTRADER_RESPALDO_DIR", "").strip()
    return Path(custom) if custom else Path(settings.data.data_dir) / "respaldos"


def state_files(settings: AppSettings) -> List[Path]:
    d = Path(settings.data.data_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix in STATE_SUFFIXES and p.name not in EXCLUDE)


def backup_state(settings: AppSettings, day: date, *, keep: int = KEEP_DEFAULT,
                 dest: Optional[Path] = None) -> Dict[str, Any]:
    """Escribe ``estado-AAAAMMDD.zip`` (reemplaza el del mismo día) y borra los más viejos que ``keep``."""
    files = state_files(settings)
    out_dir = dest if dest is not None else backup_dir(settings)
    if not files:
        return {"ok": False, "motivo": "no hay archivos de estado", "destino": str(out_dir)}
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{PREFIX}{day:%Y%m%d}.zip"
    tmp = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, arcname=p.name)
    with zipfile.ZipFile(tmp) as z:  # un respaldo que no se puede leer no es un respaldo
        bad = z.testzip()
    if bad is not None:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "motivo": f"zip dañado en {bad}", "destino": str(out_dir)}
    tmp.replace(target)
    old = sorted(out_dir.glob(f"{PREFIX}*.zip"))[:-keep] if keep > 0 else []
    for p in old:
        p.unlink(missing_ok=True)
    return {"ok": True, "archivo": str(target), "n_archivos": len(files), "bytes": target.stat().st_size,
            "borrados": len(old)}


__all__ = ["KEEP_DEFAULT", "backup_dir", "backup_state", "state_files"]
