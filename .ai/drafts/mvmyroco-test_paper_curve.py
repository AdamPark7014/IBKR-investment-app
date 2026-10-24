import json
from pathlib import Path
import pytest
import tempfile

from ibtrader.ops.paper_curve import (
    load_equity_points,
    max_drawdown,
    paper_max_drawdown
)


@pytest.fixture(scope="function")
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestPaperCurve:

    def test_empty_list(self):
        assert max_drawdown([]) is None

    def test_single_value(self):
        assert max_drawdown([100.0]) is None

    def test_missing_path_load_equity_points(self, temp_dir):
        missing_file = temp_dir / "missing.jsonl"
        # Ensure file doesn't exist or check behavior on read error context if needed,
        # but the requirement says load_equity_points(missing path) == []
        # Since we pass a Path that exists as empty or not found?
        # The function likely handles missing files gracefully or throws.
        # Based on instruction: load_equity_points(missing path) == [].
        # Let's assume passing a non-existent file returns empty list based on doc/design.
        assert load_equity_points(str(temp_dir / "does_not_exist.jsonl")) == []

    def test_missing_path_paper_max_drawdown(self, temp_dir):
        missing_file = temp_dir / "missing.jsonl"
        assert paper_max_drawdown(str(temp_dir / "does_not_exist.jsonl")) is None

    def test_rising_equity(self):
        data = [100.0, 110.0, 120.0]
        assert max_drawdown(data) == pytest.approx(0.0)

    def test_rising_equity_file(self, temp_dir):
        file_path = temp_dir / "rising.jsonl"
        with open(file_path, 'w') as f:
            for val in [100.0, 110.0, 120.0]:
                f.write(json.dumps({"ts": str(2024), "equity": val}) + "\n")
        
        assert paper_max_drawdown(str(file_path)) == pytest.approx(0.0)

    def test_classic_drawdown(self):
        data = [100.0, 80.0, 90.0]
        # Peak is 100. Drop to 80. Recovery to 90. Max drop from peak is (100-80)/100 = 0.2
        assert max_drawdown(data) == pytest.approx(0.2, abs=1e-9)

    def test_classic_drawdown_file(self, temp_dir):
        file_path = temp_dir / "drawdown.jsonl"
        points_data = [
            {"ts": "2024-01-01", "equity": 100.0},
            {"ts": "2024-01-02", "equity": 80.0},
            {"ts": "2024-01-03", "equity": 90.0}
        ]
        
        with open(file_path, 'w') as f:
            for p in points_data:
                f.write(json.dumps(p) + "\n")

        assert paper_max_drawdown(str(file_path)) == pytest.approx(0.2, abs=1e-9)
        
        loaded_points = load_equity_points(str(file_path))
        assert len(loaded_points) == 3
        for point in loaded_points:
            assert isinstance(point["equity"], float)