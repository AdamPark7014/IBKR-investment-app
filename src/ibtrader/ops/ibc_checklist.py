"""Manual paper Gateway/IBC checklist. Does not install or trade."""

from __future__ import annotations

from typing import Any

_DISCLAIMER = (
    "LOCAL CHECKLIST ONLY: review manually. "
    "Does not install IBC, restart services, place orders, or go LIVE."
)


def build_ibc_checklist() -> dict[str, Any]:
    """Safe manual checklist for local paper Gateway setup."""
    items = [
        {
            "id": "gateway_paper_port",
            "title": "Gateway paper port 4002",
            "done_hint": "Confirm API listens on 127.0.0.1:4002",
            "critical": True,
        },
        {
            "id": "api_127_only",
            "title": "API trusts only 127.0.0.1",
            "done_hint": "Trusted IPs = localhost only",
            "critical": True,
        },
        {
            "id": "read_only_api_off_for_paper_orders_if_needed",
            "title": "Read-Only API off only if paper orders needed",
            "done_hint": "Keep Read-Only on for triage-only",
            "critical": False,
        },
        {
            "id": "ibc_optional_restart",
            "title": "IBC optional for unattended Gateway restart",
            "done_hint": "Optional; paper only",
            "critical": False,
        },
        {
            "id": "no_live_until_phase3_pass",
            "title": "No LIVE until Fase 3 paper pass",
            "done_hint": "Paper mode only until gates pass",
            "critical": True,
        },
        {
            "id": "autopilot_scheduled_zero_orders",
            "title": "Autopilot scheduled with zero broker orders",
            "done_hint": "ibtrader autopilot / paper-reconcile only",
            "critical": True,
        },
    ]
    return {"phase": "paper-ops", "items": items, "disclaimer": _DISCLAIMER}


__all__ = ["build_ibc_checklist"]
