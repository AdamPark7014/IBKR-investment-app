from ibtrader.ops.paper_vs_oos import compare_paper_vs_oos


def test_dd_ok_and_kill() -> None:
    ok = compare_paper_vs_oos(
        paper_max_dd=0.10,
        paper_n_points=5,
        assumed_sharpe=0.8,
        expected_oos_max_dd=0.12,
    )
    assert ok["orders_sent"] == 0
    assert ok["dd_ok"] is True
    assert ok["kill_recommend"] is False

    bad = compare_paper_vs_oos(
        paper_max_dd=0.40,
        paper_n_points=5,
        assumed_sharpe=0.8,
        expected_oos_max_dd=0.12,
    )
    assert bad["dd_ok"] is False
    assert bad["kill_recommend"] is True


def test_kill_recommend_emits_expected_flags() -> None:
    r = compare_paper_vs_oos(
        paper_max_dd=0.50,
        paper_n_points=5,
        assumed_sharpe=0.8,
    )
    assert r["dd_ok"] is False
    assert r["kill_recommend"] is True
    # Autopilot wires Alert(code="paper_vs_oos_dd", severity="kill_recommend") when this flag is set
    assert r["orders_sent"] == 0


def test_sharpe_threshold_path() -> None:
    r = compare_paper_vs_oos(paper_max_dd=0.10, paper_n_points=2, assumed_sharpe=0.8)
    assert r["dd_ok"] is True
    assert "do not retune live" in r["notes"][0].lower()