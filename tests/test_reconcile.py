from __future__ import annotations

from pathlib import Path

from ibtrader.ops.reconcile import Fill, apply_fills, load_book, reconcile, save_book


def test_apply_fills_moves_cash_and_shares() -> None:
    book = {"cash": 10_000.0, "shares": {"SPY": 5}, "note": "x"}
    out = apply_fills(book, [Fill("SPY", "BUY", 5, 500.0, 1.0), Fill("TLT", "BUY", 10, 100.0, 1.0)])
    assert out["shares"] == {"SPY": 10, "TLT": 10}
    assert out["cash"] == 10_000 - 2_500 - 1 - 1_000 - 1
    assert out["note"] == "x"
    flat = apply_fills(out, [Fill("SPY", "SELL", 10, 510.0)])
    assert "SPY" not in flat["shares"]


def test_reconcile_detects_breaks() -> None:
    exp = {"cash": 5_000.0, "shares": {"SPY": 10, "TLT": 3}}
    ok = reconcile(exp, {"SPY": 10, "TLT": 3}, 5_010.0)
    assert ok.ok and ok.cash_diff == 10.0
    bad = reconcile(exp, {"SPY": 10, "GLD": 1}, 4_000.0)
    assert not bad.ok
    syms = {d["symbol"] for d in bad.share_diffs}
    assert syms == {"TLT", "GLD"}
    assert any(r.startswith("cash_mismatch") for r in bad.reasons)


def test_book_roundtrip_is_atomic(tmp_path: Path) -> None:
    p = tmp_path / "paper_account.json"
    assert load_book(p) is None
    save_book(p, {"cash": 1.5, "shares": {"spy": 2, "tlt": 0}})
    assert load_book(p) == {"cash": 1.5, "shares": {"SPY": 2}}
    assert not (tmp_path / "paper_account.json.tmp").exists()
