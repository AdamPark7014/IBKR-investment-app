"""Read-only check of the IB Gateway paper connection. Sends no orders.

Usage: .venv\\Scripts\\python.exe scripts\\ib_readonly_check.py

Connects with ``readonly=True`` to the configured host and paper port, and prints JSON with the account
type, number of positions and USD cash. Exit 0 when connected to a paper account (DU...), 2 otherwise.
The account id is masked so the output can be pasted in a chat or a log.
"""

from __future__ import annotations

import json
import sys

from ib_async import IB

from ibtrader.config import AppSettings

CHECK_CLIENT_ID = 991  # distinct from the trading client so the check never kicks it out


def main() -> int:
    settings = AppSettings()
    host, port = settings.ib.host, settings.ib.paper_port
    out: dict[str, object] = {"host": host, "port": port, "connected": False, "orders_sent": 0}
    ib = IB()
    try:
        ib.connect(host, port, clientId=CHECK_CLIENT_ID, timeout=8, readonly=True)
    except Exception as e:  # noqa: BLE001 - any connection failure is the answer this script reports
        out["error"] = f"{type(e).__name__}: {e}"
        out["hint"] = "Abre IB Gateway en modo Paper y activa la API en el puerto 4002 (solo localhost)."
        print(json.dumps(out, ensure_ascii=False))
        return 2
    try:
        accounts = list(ib.managedAccounts() or [])
        acct = accounts[0] if accounts else ""
        is_paper = acct.startswith("DU")
        values = ib.accountValues()
        cash = next((float(v.value) for v in values if v.tag == "TotalCashValue" and v.currency == "USD"), None)
        out.update(
            connected=True,
            account=f"{acct[:2]}...{acct[-2:]}" if acct else "",
            is_paper=is_paper,
            positions=len(ib.positions()),
            cash_usd=cash,
        )
        print(json.dumps(out, ensure_ascii=False))
        return 0 if is_paper else 2
    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
