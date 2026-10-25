from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import pytest
from ibtrader.ops.urgency_age import load_open_order_age_seconds


@pytest.fixture
def tmp_path(request):
    return request.param or request.getfixturevalue("tmp_path")


class TestLoadOpenOrderAgeSeconds:

    def test_missing_file_returns_zero(self, tmp_path):
        path = Path("/nonexistent/file.json")
        assert load_open_order_age_seconds(path) == 0.0

    def test_age_seconds_key(self, tmp_path):
        data = {"age_seconds": 12.5}
        file = tmp_path / "order.json"
        file.write_text("{" + repr(data).replace("'", '"') + "}")
        assert load_open_order_age_seconds(file) == 12.5

    def test_opened_at_iso_with_injected_now(self, tmp_path):
        opened_at = "2024-06-01T12:00:00Z"
        file = tmp_path / "order.json"
        content = '{"opened_at": ' + repr(opened_at) + ", }"
        # Manually fix JSON syntax inside the string to be valid
        import json
        obj = {"opened_at": opened_at}
        file.write_text(json.dumps(obj))

        now = datetime(2024, 6, 1, 12, 0, 30, tzinfo=timezone.utc)
        result = load_open_order_age_seconds(file, now=now)
        assert result == pytest.approx(30.0)