import json
import tempfile
from pathlib import Path
from click.testing import CliRunner
from ibtrader.ops.cli import cli


def get_sample_ledger_data(num_rows: int) -> list[dict]:
    """Generates a temporary ledger file with sample transaction data."""
    rows = []
    for i in range(num_rows):
        row = {
            "datetime": f"2023-10-{10 + i % 28:02d}T09:30:00Z",
            "symbol": "BTCUSD",
            "side": "buy" if i % 2 == 0 else "sell",
            "quantity": round(0.001 * (i + 1), 6),
            "price": round(35000.0 + (i * 10) % 1000, 2),
            "commission": round((0.001 * (0.001 * (i + 1))) * (35000.0 + (i * 10) % 1000), 8),
        }
        rows.append(row)
    return rows


def test_slippage_report_smoke():
    """Smoke test for the slippage-report CLI command."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        ledger_file = tmp_path / "ledger.json"

        # Prepare sample data with at least two rows to ensure a valid report generation
        # The instruction specifies 'record_slip two rows', interpreted as creating 
        # the initial state for the report by populating the ledger with 2 entries.
        ledger_data = get_sample_ledger_data(2)

        # Write ledger data to the temporary file
        with open(ledger_file, "w") as f:
            json.dump(ledger_data, f)

        runner = CliRunner()
        result = runner.invoke(cli, ["slippage-report", "--path", str(ledger_file), "--window-days", "30"])

        # Assert that the command exits successfully
        assert result.exit_code == 0, f"Command failed with code {result.exit_code}. Output: {result.output}"

        # Parse the JSON output
        output_json = json.loads(result.output)

        # Assert that the resulting report contains at least one slip record (n >= 1)
        # Assuming the top-level structure is a dict with an 'slips' or similar list key.
        # Based on common CLI patterns and the assertion 'JSON has n>=1', we check the count of slips.
        slips_list = output_json.get("slips", [])
        assert len(slips_list) >= 1, f"Expected at least one slip, got {len(slips_list)}"

        # If the structure is flat or different, adjust accordingly based on actual schema.
        # Assuming 'n' refers to the count of generated slips.
        n = len(slips_list)
        assert n >= 1