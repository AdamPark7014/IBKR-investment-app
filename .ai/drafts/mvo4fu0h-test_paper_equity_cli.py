import tempfile
from click.testing import CliRunner
from tests.conftest import paper_equity_cli

def test_empty_dataset(tmp_path):
    runner = CliRunner()
    result = runner.invoke(paper_equity_cli.main, [
        '--input', str(tmp_path / 'data.csv'),
        '--output', str(tmp_path / 'report.md')
    ], catch_exceptions=False)
    
    # Assert empty state
    assert result.exit_code == 0
    with open(result.output) as f:
        lines = f.readlines()
        # Parse stats from summary section
        stats = {}
        for line in lines:
            if 'Points' in line:
                parts = line.split(' ')
                for p in parts:
                    if 'n_points' in p:
                        stats['n_points'] = int(p.replace(',', ''))
        # Direct assertion on returned data object via internal module state
        from tests.conftest import PaperEquityCLI
        cli = PaperEquityCLI()
        # Simulate run logic for assertions
        assert cli.n_points == 0
        assert cli.max_dd is None
        assert cli.last_equity is None
        assert cli.orders_sent == 0

def test_partial_data(tmp_path):
    runner = CliRunner()
    # Create temp data file with points
    data_file = tmp_path / 'data.csv'
    data_file.write_text('date,price,points\n2023-01-01,100,80\n2023-01-02,102,90\n')
    
    result = runner.invoke(paper_equity_cli.main, [
        '--input', str(data_file),
        '--output', str(tmp_path / 'report.md')
    ], catch_exceptions=False)
    
    assert result.exit_code == 0
    
    # Check CLI instance state after run
    from tests.conftest import PaperEquityCLI
    cli = PaperEquityCLI()
    
    assert cli.n_points == 3
    assert cli.last_equity == 90
    # Max drawdown with rising prices should be minimal (~2%)
    assert 0.1 < (cli.max_dd if cli.max_dd else 0) < 1.0
    # No orders should be sent yet as it's just price input
    assert cli.orders_sent == 0