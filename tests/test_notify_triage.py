"""Alerts, heartbeat and Claude triage with fakes (audit 2026-11-07, §3.6 and §6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from ibtrader.config import OpsConfig
from ibtrader.intelligence import triage as tr
from ibtrader.ops.notify import check_heartbeat, emit_alert, write_heartbeat

NOW = datetime(2026, 11, 9, 22, 0, tzinfo=timezone.utc)


def _ops(tmp: Path, **kw: Any) -> OpsConfig:
    return OpsConfig(alerts_file=str(tmp / "alerts.jsonl"), heartbeat_file=str(tmp / "hb.json"), **kw)


def test_alert_written_and_no_telegram_without_token(tmp_path: Path) -> None:
    calls: List[Any] = []
    row = emit_alert(_ops(tmp_path), "data_quality", "warn", "stale", {"sym": "SPY"},
                     post=lambda *a, **k: calls.append(k), now=NOW)
    assert row["delivery"] is None and calls == []
    saved = json.loads((tmp_path / "alerts.jsonl").read_text().splitlines()[0])
    assert saved["code"] == "data_quality" and saved["context"] == {"sym": "SPY"}


def test_alert_telegram_and_delivery_never_raises(tmp_path: Path) -> None:
    cfg = _ops(tmp_path, telegram_bot_token="t", telegram_chat_id="c")
    sent: List[Dict[str, Any]] = []
    row = emit_alert(cfg, "x", "critical", "boom",
                     post=lambda url, json, timeout: sent.append(json) or SimpleNamespace(status_code=200), now=NOW)
    assert row["delivery"] == "sent" and "CRÍTICO" in sent[0]["text"]

    def bad(*_a: Any, **_k: Any) -> Any:
        raise ConnectionError("down")

    assert emit_alert(cfg, "x", "warn", "m", post=bad, now=NOW)["delivery"] == "error: ConnectionError"
    assert "delivery" not in emit_alert(cfg, "x", "info", "m", post=bad, now=NOW)  # info is file-only


def test_heartbeat_fresh_stale_missing(tmp_path: Path) -> None:
    cfg = _ops(tmp_path)
    assert check_heartbeat(cfg, now=NOW)["reason"] == "heartbeat_missing"
    write_heartbeat(cfg, {"status": "ok"}, now=NOW - timedelta(hours=2))
    assert check_heartbeat(cfg, now=NOW)["ok"] is True
    out = check_heartbeat(cfg, now=NOW + timedelta(hours=40))
    assert out["ok"] is False and out["alert"]["severity"] == "critical"


class FakeClient:
    def __init__(self, text: str, stop: str = "end_turn") -> None:
        self.kw: Dict[str, Any] = {}
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
        )

        def create(**kw: Any) -> Any:
            self.kw = kw
            return resp

        self.messages = SimpleNamespace(create=create)


GOOD = json.dumps({"severity": "warn", "likely_cause": "token vencido", "runbook_step": "revisar token",
                   "needs_human": True})


def test_triage_valid_json_and_usage_logged(tmp_path: Path) -> None:
    c = FakeClient(GOOD)
    t = tr.triage_incident({"step": "load"}, data_dir=tmp_path, client=c)
    assert t is not None and t.severity == "warn"
    assert c.kw["model"] == tr.TRIAGE_MODEL
    assert "temperature" not in c.kw and c.kw["output_config"]["effort"] == "medium"
    assert c.kw["output_config"]["format"]["schema"]["additionalProperties"] is False
    row = json.loads((tmp_path / "ai_usage.jsonl").read_text().splitlines()[0])
    assert row["usd"] == pytest.approx((1000 * 2.0 + 200 * 10.0) / 1e6)
    assert tr.monthly_spend(tmp_path) == pytest.approx(row["usd"])


def test_triage_refusal_and_bad_json_return_none(tmp_path: Path) -> None:
    assert tr.triage_incident({}, data_dir=tmp_path, client=FakeClient(GOOD, stop="refusal")) is None
    assert tr.triage_incident({}, data_dir=tmp_path, client=FakeClient("{not json")) is None
    assert tr.review_diff("diff", data_dir=tmp_path, client=FakeClient('{"verdict":"maybe","findings":[]}')) is None


def test_no_puerta_means_no_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert tr.triage_incident({}, data_dir=tmp_path) is None
    row = json.loads((tmp_path / "ai_usage.jsonl").read_text().splitlines()[0])
    assert row["status"] == "puerta_not_configured"
