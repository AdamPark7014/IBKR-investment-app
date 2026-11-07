"""Claude for incident triage and code review, only through the puerta (audit 2026-11-07, §6).

Rules this module enforces (and tests pin):

* Never in the order path. ``triage_incident`` and ``review_diff`` read facts that are already
  computed and return a suggestion; nothing here writes data, config or the kill switch.
* Only through the puerta (``puerta_config_error``); the real Anthropic key never lives here.
* Structured outputs (``output_config.format`` + JSON Schema), validated with Pydantic; any
  failure (no puerta, API error, refusal, truncation, invalid JSON) returns ``None`` and the
  caller keeps its deterministic alert.
* Explicit ``effort``; no ``temperature``/``top_p``/``top_k`` (rejected by API 2026-10-21);
  stable system prompt first with ``cache_control``; sorted JSON facts after it.
* Every call (ok or not) is appended to ``data/ai_usage.jsonl`` with model, token counts and an
  estimated USD cost; ``monthly_spend`` lets the caller stop at ``OPS__AI_MONTHLY_BUDGET_USD``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, ValidationError

from .brief import puerta_config_error

TRIAGE_MODEL = "claude-sonnet-5-5"
REVIEW_MODEL = "claude-opus-5-5"
#: USD per million tokens (input, output), list price 2026-11-07.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


class Triage(BaseModel):
    severity: Literal["info", "warn", "critical"]
    likely_cause: str
    runbook_step: str
    needs_human: bool


class ReviewFinding(BaseModel):
    file: str
    category: Literal["lookahead", "leakage", "risk_bypass", "risk_default_change", "truncation",
                      "order_path", "secret", "other"]
    severity: Literal["low", "medium", "high"]
    explanation: str


class Review(BaseModel):
    verdict: Literal["ok", "needs_changes", "block"]
    findings: List[ReviewFinding]


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """Pydantic schema → strict JSON Schema (no extra keys anywhere, every field required)."""
    schema = model.model_json_schema()

    def fix(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = list(node["properties"])
            node.pop("title", None)
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


TRIAGE_SYSTEM = (
    "You triage operational incidents of ibtrader, a daily-rebalanced ETF system on Interactive Brokers. "
    "You receive FACTS as JSON: the failing step, error text, recent alerts, kill-switch and mode. "
    "Reply only with the requested JSON. severity: critical if money or positions may be wrong or orders may "
    "be duplicated; warn if the run was blocked safely; info otherwise. likely_cause: one sentence grounded "
    "in the facts; say 'unknown' rather than guess. runbook_step: the single next manual check for the "
    "operator. Never suggest disabling risk checks, retuning the strategy, or sending orders by hand. "
    "Answer in Spanish."
)

REVIEW_SYSTEM = (
    "You review diffs of ibtrader, a Python trading system (daily ETF rebalancing on IBKR). Look only for: "
    "look-ahead (using data at t to decide at t or earlier, missing shift, fitting on the full sample), "
    "leakage between train/validation/hold-out, any path that sends orders without risk.pretrade, changed "
    "default risk limits or gates, truncated or half-written files, secrets in code, and changes to the order "
    "path. Ignore style. verdict: block if any high finding, needs_changes if any medium, else ok. Explain each "
    "finding in Spanish, one or two sentences, citing the file."
)


def _usage_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "ai_usage.jsonl"


def monthly_spend(data_dir: str | Path, now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)
    p = _usage_path(data_dir)
    if not p.is_file():
        return 0.0
    month = now.strftime("%Y-%m")
    total = 0.0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("ts", "")).startswith(month):
            total += float(row.get("usd") or 0.0)
    return total


def _log_usage(data_dir: str | Path, row: Mapping[str, Any]) -> None:
    p = _usage_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":"), default=str) + "\n")


def _call(
    *,
    proceso: str,
    model: str,
    system: str,
    payload: str,
    schema: Dict[str, Any],
    effort: str,
    max_tokens: int,
    data_dir: str | Path,
    budget_usd: float,
    client: Any = None,
) -> Optional[str]:
    """One structured-output call through the puerta. Returns the JSON text or None."""
    base_row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "proceso": proceso,
        "model": model,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
    }
    if client is None:
        problem = puerta_config_error()
        if problem is not None:
            _log_usage(data_dir, {**base_row, "status": "puerta_not_configured", "usd": 0.0})
            return None
        if monthly_spend(data_dir) >= budget_usd:
            _log_usage(data_dir, {**base_row, "status": "budget_exhausted", "usd": 0.0})
            return None
        try:
            import anthropic
        except ImportError:
            _log_usage(data_dir, {**base_row, "status": "sdk_missing", "usd": 0.0})
            return None
        client = anthropic.Anthropic()  # ANTHROPIC_BASE_URL (puerta) + ANTHROPIC_API_KEY (pia_ token)
    try:
        r = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": payload}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            extra_headers={"x-proceso": proceso},
        )
    except Exception as exc:  # noqa: BLE001 - fail closed to the deterministic path
        _log_usage(data_dir, {**base_row, "status": f"error:{type(exc).__name__}", "usd": 0.0})
        return None
    usage = getattr(r, "usage", None)
    tin = int(getattr(usage, "input_tokens", 0) or 0) + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    tcache = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    tout = int(getattr(usage, "output_tokens", 0) or 0)
    pin, pout = PRICES.get(model, (4.0, 20.0))
    usd = (tin * pin + tcache * pin * 0.1 + tout * pout) / 1e6
    stop = getattr(r, "stop_reason", None)
    _log_usage(data_dir, {**base_row, "status": f"stop:{stop}", "input_tokens": tin, "cache_read_tokens": tcache,
                          "output_tokens": tout, "usd": round(usd, 6)})
    if stop in ("refusal", "max_tokens"):
        return None
    return "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", None) == "text") or None


def triage_incident(
    facts: Mapping[str, Any], *, data_dir: str | Path = "./data", budget_usd: float = 10.0, client: Any = None
) -> Optional[Triage]:
    text = _call(
        proceso="ibtrader-triage", model=TRIAGE_MODEL, system=TRIAGE_SYSTEM,
        payload=json.dumps(dict(facts), sort_keys=True, ensure_ascii=False, default=str),
        schema=_schema(Triage), effort="medium", max_tokens=2000, data_dir=data_dir, budget_usd=budget_usd,
        client=client,
    )
    if not text:
        return None
    try:
        return Triage.model_validate_json(text)
    except ValidationError:
        return None


def review_diff(
    diff: str, *, data_dir: str | Path = "./data", budget_usd: float = 10.0, client: Any = None
) -> Optional[Review]:
    text = _call(
        proceso="ibtrader-review", model=REVIEW_MODEL, system=REVIEW_SYSTEM, payload=diff,
        schema=_schema(Review), effort="high", max_tokens=16000, data_dir=data_dir, budget_usd=budget_usd,
        client=client,
    )
    if not text:
        return None
    try:
        return Review.model_validate_json(text)
    except ValidationError:
        return None


__all__ = ["Review", "ReviewFinding", "Triage", "monthly_spend", "review_diff", "triage_incident"]
