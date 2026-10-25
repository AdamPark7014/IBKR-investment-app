from __future__ import annotations
import pytest
from ibtrader.ops.paper_vs_oos.compare_paper_vs_oos import compare_paper_vs_oos


class TestComparePaperVsOOS:
    def test_dd_ok_with_expected_oos(self):
        paper_max_dd = 0.10
        expected_oos_max_dd = 0.10
        dd_ok, kill_recommend, orders_sent = compare_paper_vs_oos(
            sharpe_based_path=(1, -0.09),
            paper_max_dd=paper_max_dd,
            expected_oos_max_dd=expected_oos_max_dd
        )
        assert dd_ok is True
        assert kill_recommend is False
        assert orders_sent == 0

    def test_dd_not_ok_exceeds_expected(self):
        paper_max_dd = 0.50
        expected_oos_max_dd = 0.10
        dd_ok, kill_recommend, orders_sent = compare_paper_vs_oos(
            sharpe_based_path=(1, -0.45),
            paper_max_dd=paper_max_dd,
            expected_oos_max_dd=expected_oos_max_dd
        )
        assert dd_ok is False
        assert kill_recommend is True
        assert orders_sent == 0

    def test_orders_sent_always_zero(self):
        paper_max_dd = None
        result = compare_paper_vs_oos(
            sharpe_based_path=(1, -0.05),
            paper_max_dd=paper_max_dd,
            expected_oos_max_dd=0.20
        )
        assert result[2] == 0

    def test_kill_recommend_sharpe_breach(self):
        paper_max_dd = 0.40
        assumed_sharpe = 0.8
        # Simulate breach by negative return relative to assumption
        dd_ok, kill_recommend, orders_sent = compare_paper_vs_oos(
            sharpe_based_path=(1, -0.5),
            paper_max_dd=paper_max_dd,
            expected_oos_max_dd=0.20
        )
        assert kill_recommend is True