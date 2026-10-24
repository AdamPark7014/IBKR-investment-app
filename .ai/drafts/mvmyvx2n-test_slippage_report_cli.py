import json
import subprocess
from pathlib import Path
from click.testing import CliRunner
from ibtrader.ops.cli import cli
from ibtrader.slippage.core import SlippageModel

# Test configuration
TEST_WINDOW_DAYS = 30

def test_slippage_report_cli(tmp_path):
    """Smoke test for the slippage report CLI command."""
    
    # Define a minimal valid configuration file for the test
    config_content = {
        "slippage_model": {
            "model_type": "constant",
            "parameters": {
                "slippage_fixed_bps": 10,
                "execution_time_window": TEST_WINDOW_DAYS
            }
        }
    }
    
    config_file_path = tmp_path / "test_slippage_config.json"
    with open(config_file_path, "w") as f:
        json.dump(config_content, f)
    
    ledger_data = {
        "account_id": "TEST_ACCOUNT_001",
        "strategy_name": "TestStrategy",
        "data_points": 50  # Ensure we have enough data for the window
    }
    
    ledger_path = tmp_path / "test_ledger.json"
    with open(ledger_path, "w") as f:
        json.dump(ledger_data, f)
    
    # Run the CLI command
    runner = CliRunner()
    result = runner.invoke(cli, [
        "slippage-report", 
        "--path", str(ledger_path),
        "--window-days", str(TEST_WINDOW_DAYS),
        "--config", str(config_file_path)
    ])
    
    # Assert successful exit code
    assert result.exit_code == 0, f"CLI command failed with message: {result.output}"
    
    # Parse the JSON output from stdout
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError as e:
        pytest.fail(f"CLI output is not valid JSON:\n{result.output}\nError: {e}")
    
    # Assert that 'n' exists in the payload and is greater than or equal to 1
    assert "n" in payload, f"'n' key missing from CLI output payload: {payload}"
    n = payload["n"]
    assert isinstance(n, (int, float)), f"Expected 'n' to be numeric, got type: {type(n)}"
    assert n >= 1, f"Expected number of records 'n' to be >= 1, but got {n}"
    
    print(f"Smoke test passed successfully. Number of records found (n): {n}")
    print(f"Output payload: {payload}")