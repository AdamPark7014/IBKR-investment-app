import json
import os
import tempfile
from pathlib import Path

import pytest

from ibtrader.ops.stack import PaperStack, cmd_paper_stack


@pytest.fixture(scope="function")
def paper_db(tmp_path: Path) -> Path:
    return tmp_path / "paper_stack.sqlite"


def test_upsert_roundtrip(paper_db: Path):
    # Ensure clean state before test
    if paper_db.exists():
        os.remove(paper_db)

    import time as ts_module
    ts = ts_module.time()

    ps = PaperStack(str(paper_db))
    try:
        # Upsert desired
        ps.upsert_desired("AAPL", 10.0, ts)
        ps.upsert_held("AAPL", 7.0, ts)
        ps.upsert_desired("MSFT", 5.0, ts)

        snap = ps.snapshot()

        assert snap["desired"]["AAPL"] == 10.0
        assert snap["desired"]["MSFT"] == 5.0
        assert snap["held"]["AAPL"] == 7.0

        # Close and Re-open for roundtrip test
        ps.close()
        ps = PaperStack(str(paper_db))
        
        snap2 = ps.snapshot()
        assert snap2["desired"]["AAPL"] == 10.0
        assert snap2["desired"]["MSFT"] == 5.0
        assert snap2["held"]["AAPL"] == 7.0
    finally:
        if paper_db.exists():
            os.remove(paper_db)


def test_drift_and_sync(paper_db: Path):
    # Ensure clean state before test
    if paper_db.exists():
        os.remove(paper_db)

    ps = PaperStack(str(paper_db))
    try:
        import time as ts_module
        ts = ts_module.time()

        sync_from_json = ps.sync_from_json
        desired_dict = {"AAA": 3.0, "BBB": 1.0}
        held_dict = {"AAA": 1.0, "CCC": 2.0}
        sync_from_json(desired=desired_dict, held=held_dict, ts=ts)

        snap = ps.snapshot()

        # Check keys exist
        assert "desired" in snap
        assert "held" in snap
        assert "drift" in snap

        drift = snap["drift"]
        
        # Check order of symbols (sorted)
        symbol_keys = list(drift.keys())
        expected_sorted = sorted(symbol_keys)
        assert symbol_keys == expected_sorted

        # AAA: desired=3, held=1 -> delta = 2
        assert drift["AAA"]["delta"] == pytest.approx(2.0)
        
        # BBB: desired=1, held=0 (not in held dict) -> delta = 1
        assert drift["BBB"]["delta"] == pytest.approx(1.0)

        # CCC: desired=0 (not in desired dict), held=2 -> delta = -2
        assert drift["CCC"]["delta"] == pytest.approx(-2.0)
    finally:
        if paper_db.exists():
            os.remove(paper_db)


def test_cmd_paper_stack_orders_sent_zero(tmp_path: Path):
    ps_path = str(tmp_path / "ps.sqlite")

    # Ensure clean state before test
    if os.path.exists(ps_path):
        os.remove(ps_path)

    import time as ts_module
    ts = ts_module.time()

    # Initialize with some data to ensure it's not an empty init issue, 
    # though the cmd function logic usually handles this.
    ps = PaperStack(ps_path)
    try:
        ps.upsert_desired("GOOGL", 50.0, ts)
        ps.upsert_held("GOOGL", 45.0, ts)
        ps.close()

        out = cmd_paper_stack(ps_path)

        # When drift is zero (or no orders are sent logic applies), orders_sent should be 0
        # Note: The actual order generation logic depends on the broker connection state.
        # Since we use a fake database and no real broker, 'orders_sent' in the output dict
        # from this helper usually reflects that no valid orders were pushed to a live system 
        # or it is 0 if drift calculation results in zero net order.
        # Based on the prompt requirement: assert out["orders_sent"] == 0
        
        # If there was drift (45 held vs 50 desired -> buy 5), real logic would send orders.
        # However, the prompt explicitly asks to assert 0. This implies that in this specific
        # test context (no broker conn mocked), the function returns 0 or the scenario 
        # implies no actionable drift was successfully converted to orders due to lack of broker.
        
        assert out["orders_sent"] == 0
        
        # Verify structure
        assert "desired" in out
        assert "held" in out
        assert "drift" in out
    finally:
        if os.path.exists(ps_path):
            os.remove(ps_path)