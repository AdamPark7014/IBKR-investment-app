"""Alerts and heartbeat (audit 2026-11-07, §3.6 and §5 step 7).

* ``emit_alert`` appends to ``data/alerts.jsonl`` and, when ``OPS__TELEGRAM_BOT_TOKEN`` and
  ``OPS__TELEGRAM_CHAT_ID`` are set, sends the text to Telegram. Delivery never raises: an
  alert channel that can crash the run would be worse than no channel.
* ``write_heartbeat`` records the last successful run; ``check_heartbeat`` (run by a separate
  scheduled task) turns a missing or old heartbeat into a critical alert: the "dead man's
  switch" that notices when the daily job silently stopped.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from ..config import OpsConfig

SEVERITIES = ("info", "warn", "critical")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _urllib_post(url: str, json: Mapping[str, Any], timeout: float) -> Any:
    import json as _json
    import urllib.request

    req = urllib.request.Request(url, data=_json.dumps(dict(json)).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return type("R", (), {"status_code": resp.status})()


def _telegram(cfg: OpsConfig, text: str, post: Optional[Callable[..., Any]] = None) -> Optional[str]:
    if not (cfg.telegram_bot_token and cfg.telegram_chat_id):
        return None
    try:
        sender = post or _urllib_post
        r = sender(
            f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage",
            json={"chat_id": cfg.telegram_chat_id, "text": text[:4000], "disable_web_page_preview": True},
            timeout=10,
        )
        code = getattr(r, "status_code", 200)
        return "sent" if 200 <= int(code) < 300 else f"http_{code}"
    except Exception as exc:  # noqa: BLE001 - never let delivery kill the run
        return f"error: {type(exc).__name__}"


def emit_alert(
    cfg: OpsConfig,
    code: str,
    severity: str,
    message: str,
    context: Optional[Mapping[str, Any]] = None,
    *,
    post: Optional[Callable[..., Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    sev = severity if severity in SEVERITIES else "warn"
    row: Dict[str, Any] = {
        "ts": (now or _now()).isoformat(),
        "code": code,
        "severity": sev,
        "message": message,
        "context": dict(context or {}),
    }
    if sev != "info":
        row["delivery"] = _telegram(cfg, f"[ibtrader {sev.upper()}] {code}: {message}", post)
    p = Path(cfg.alerts_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
    return row


def write_heartbeat(cfg: OpsConfig, payload: Mapping[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    row = {"ts": (now or _now()).isoformat(), **dict(payload)}
    p = Path(cfg.heartbeat_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(row, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return row


def check_heartbeat(
    cfg: OpsConfig,
    *,
    max_age_hours: float = 30.0,
    now: Optional[datetime] = None,
    post: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """``ok`` False (and a critical alert) when the heartbeat is missing, unreadable or too old."""
    now = now or _now()
    p = Path(cfg.heartbeat_file)
    reason: Optional[str] = None
    last: Optional[str] = None
    if not p.is_file():
        reason = "heartbeat_missing"
    else:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            last = str(raw.get("ts"))
            ts = datetime.fromisoformat(last)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if now - ts > timedelta(hours=max_age_hours):
                reason = f"heartbeat_stale: last {last}"
        except (OSError, ValueError, json.JSONDecodeError):
            reason = "heartbeat_unreadable"
    out: Dict[str, Any] = {"ok": reason is None, "last": last, "reason": reason}
    if reason is not None:
        out["alert"] = emit_alert(cfg, "heartbeat", "critical",
                                  f"daily run did not report ({reason})", post=post, now=now)
    return out


__all__ = ["SEVERITIES", "check_heartbeat", "emit_alert", "write_heartbeat"]
