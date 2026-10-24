# This file serves as a manual checklist for Adam's local development environment. It is NOT an automated installer, script runner, or order placer. Do not run this to install IBC or connect to live markets. Review each item in your terminal manually before proceeding.

from __future__ import annotations
import json
from typing import Any


def build_ibc_checklist() -> dict[str, Any]:
    """Builds a safe, manual checklist for the local Phase 1 (Paper) Gateway setup."""
    disclaimer_text = "LOCAL CHECKLIST ONLY: Review these items manually in your terminal. This script does not install IBC, restart services, place orders, or connect to live markets."

    items_data = [
        {
            "id": "gateway_paper_port",
            "title": "Verify Gateway binds to paper port 4002 (127.0.0.1:4002)",
            "done_hint": "Run 'netstat -ano | findstr :4002' and ensure only 'ibtrader' listens on local IPv4.",
            "critical": True,
        },
        {
            "id": "api_127_only",
            "title": "Ensure API binds/trusts ONLY 127.0.0.1",
            "done_hint": "Check Gateway config for 'trusted_ips' containing only ['127.0.0.1'] or default localhost binding.",
            "critical": True,
        },
        {
            "id": "read_only_api_off_for_paper_orders_if_needed",
            "title": "Read-Only API disabled ONLY if paper order placement is needed",
            "done_hint": "Confirm 'enable_read_only' is False only if you intend to place simulated orders.",
            "critical": False,
        },
        {
            "id": "ibc_optional_restart",
            "title": "IBC optional for unattended Gateway restart (Paper only)",
            "done_hint": "Note that 'ibtrader' is a local dev tool; do not run in production clusters.",
            "critical": False,
        },
        {
            "id": "no_live_until_phase3_pass",
            "title": "NO LIVE trading until Phase 3 passes manual safety checks",
            "done_hint": "Ensure 'paper_mode' is True and live credentials are not injected.",
            "critical": True,
        },
        {
            "id": "autopilot_scheduled_zero_orders",
            "title": "Autopilot scheduled but zero broker orders active",
            "done_hint": "Check job scheduler; ensure no scheduled tasks have active order IDs or non-zero quantities.",
            "critical": True,
        },
    ]

    return {
        "phase": "paper-ops",
        "items": items_data,
        "disclaimer": disclaimer_text,
    }


__all__ = ["build_ibc_checklist"]