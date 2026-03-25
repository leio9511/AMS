import pytest
from unittest.mock import patch, MagicMock
from scripts.qmt_client import QMTClient

def test_get_full_tick():
    with patch("httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"600000.SH": {"lastPrice": 10.0, "volume": 1000}}
        mock_get.return_value = mock_resp

        client = QMTClient()
        res = client.get_full_tick()
        assert res == {"600000.SH": {"lastPrice": 10.0, "volume": 1000}}
        mock_get.assert_called_once_with("http://43.134.76.215:8000/api/bulk_quote")
