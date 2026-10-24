import math
from ibtrader.ops.alerts import Alert, evaluate_paper_alerts


def test_always_has_triage_disclaimer():
    result = evaluate_paper_alerts()
    assert len(result) > 0
    for alert in result:
        if alert.severity == "info":
            assert alert.message.find("triage_disclaimer") != -1
            return


def test_orders_sent_warn():
    input_dict = {"orders_sent": 1}
    result = evaluate_paper_alerts(input_dict)
    warn_found = False
    for alert in result:
        if alert.severity == "warn" and "orders_unexpected" in alert.message:
            warn_found = True
    assert warn_found


def test_paper_drift_warn():
    input_dict_high = {"n_drift": 5}
    input_dict_low = {"n_drift": 4}

    result_high = evaluate_paper_alerts(input_dict_high)
    result_low = evaluate_paper_alerts(input_dict_low)

    drift_found_high = any("paper_drift" in a.message for a in result_high)
    drift_found_low = any("paper_drift" in a.message for a in result_low)

    assert drift_found_high is True
    assert drift_found_low is False


def test_dd_vs_sharpe_kill():
    assumed_sharpe = 0.8
    max_drawdown_1 = 0.36
    max_drawdown_2 = 0.20

    threshold = min(0.35, 0.15 + 0.25 / max(assumed_sharpe, 0.1))
    
    input_dict_high = {"max_drawdown": max_drawdown_1}
    input_dict_low = {"max_drawdown": max_drawdown_2}

    result_high = evaluate_paper_alerts(input_dict_high)
    result_low = evaluate_paper_alerts(input_dict_low)

    dd_rule_found_high = any("dd_vs_sharpe" in a.message for a in result_high)
    dd_rule_found_low = any("dd_vs_sharpe" in a.message for a in result_low)

    assert dd_rule_found_high is True
    assert dd_rule_found_low is False


def test_max_drawdown_none_skips_dd_rule():
    input_dict = {"max_drawdown": None}
    result = evaluate_paper_alerts(input_dict)
    dd_rule_found = any("dd_vs_sharpe" in a.message for a in result)
    assert dd_rule_found is False