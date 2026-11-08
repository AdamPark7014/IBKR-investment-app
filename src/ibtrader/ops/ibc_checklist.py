"""Lista manual para el Gateway/IBC en paper. No instala nada ni opera."""

from __future__ import annotations

from typing import Any

_DISCLAIMER = (
    "SOLO LISTA LOCAL: revísala a mano. "
    "No instala IBC, no reinicia servicios, no envía órdenes ni pasa a real."
)


def build_ibc_checklist() -> dict[str, Any]:
    """Safe manual checklist for local paper Gateway setup."""
    items = [
        {
            "id": "gateway_paper_port",
            "title": "Gateway en modo paper, puerto 4002",
            "done_hint": "API → Enable ActiveX and Socket Clients, puerto 4002; lo comprueba `ibtrader chequeo`",
            "critical": True,
        },
        {
            "id": "api_127_only",
            "title": "La API solo confía en 127.0.0.1",
            "done_hint": "Trusted IPs = solo localhost",
            "critical": True,
        },
        {
            "id": "read_only_api_off_for_paper_orders_if_needed",
            "title": "Read-Only API apagado solo cuando toque enviar órdenes paper",
            "done_hint": "Déjalo encendido mientras sigas en modo sombra",
            "critical": False,
        },
        {
            "id": "ibc_optional_restart",
            "title": "IBC opcional para reiniciar el Gateway sin intervención",
            "done_hint": "Opcional; solo paper",
            "critical": False,
        },
        {
            "id": "no_live_until_phase3_pass",
            "title": "Nada en real hasta pasar el scorecard en paper",
            "done_hint": "MODE=PAPER hasta que el scorecard dé ready_for_live",
            "critical": True,
        },
        {
            "id": "run_daily_scheduled_shadow",
            "title": "run-daily plan/execute + heartbeat-check programados (primero EXECUTION__MODE=shadow)",
            "done_hint": "pwsh -File scripts/schedule-run-daily.ps1 -Action Register",
            "critical": True,
        },
    ]
    return {"phase": "paper-ops", "items": items, "disclaimer": _DISCLAIMER}


__all__ = ["build_ibc_checklist"]
