"""The single gateway to Claude (the "puerta"): ibtrader never holds the Anthropic key.

Only ``puerta_config_error`` lives here; ``intelligence.triage`` is the one module that calls Claude.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional
from urllib.parse import urlparse

#: Hosts of the single gateway to Claude (C:\dev\scripts\ai-os\IA-CLAUDE.md). Nothing else is allowed.
PUERTA_HOSTS = ("ia.zynoratek.com", "puerta-ia:8080")
PUERTA_TOKEN_PREFIX = "pia_"


def puerta_config_error(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Why Claude cannot be called, or None when the environment points at the puerta.

    ibtrader never holds the Anthropic key: ``ANTHROPIC_BASE_URL`` must be the puerta and
    ``ANTHROPIC_API_KEY`` the project token (``pia_ibtrader_…``). The key itself is never printed.
    """
    e = os.environ if env is None else env
    base = str(e.get("ANTHROPIC_BASE_URL") or "").strip()
    key = str(e.get("ANTHROPIC_API_KEY") or "").strip()
    if not base:
        return "falta ANTHROPIC_BASE_URL: Claude solo va por la puerta (https://ia.zynoratek.com)"
    host = (urlparse(base).netloc or "").lower()
    if host not in PUERTA_HOSTS:
        return f"ANTHROPIC_BASE_URL apunta a {host or base!r}, no a la puerta ({', '.join(PUERTA_HOSTS)})"
    if not key:
        return "falta ANTHROPIC_API_KEY (el token del proyecto pia_… de la puerta)"
    if not key.startswith(PUERTA_TOKEN_PREFIX):
        return "ANTHROPIC_API_KEY no es un token de la puerta (pia_…); nunca la clave real de Anthropic"
    return None


__all__ = ["PUERTA_HOSTS", "PUERTA_TOKEN_PREFIX", "puerta_config_error"]
