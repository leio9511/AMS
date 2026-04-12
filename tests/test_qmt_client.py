import pytest
from unittest.mock import patch, MagicMock
from scripts.qmt_client import QMTClient

def test_get_full_tick():
    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success", "data": {"600000.SH": {"lastPrice": 10.0, "volume": 1000}}}
        mock_post.return_value = mock_resp

        client = QMTClient()
        res = client.get_full_tick()
        assert res == {"600000.SH": {"lastPrice": 10.0, "volume": 1000}}
        mock_post.assert_called_once_with(
            "http://43.134.76.215:8000/api/xtdata_call",
            json={"method": "get_full_tick", "args": [], "kwargs": {}}
        )

def test_get_full_tick_with_code_list():
    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success", "data": {"000001.SZ": {"lastPrice": 10.0}}}
        mock_post.return_value = mock_resp

        client = QMTClient()
        res = client.get_full_tick(code_list=["000001.SZ"])
        assert res == {"000001.SZ": {"lastPrice": 10.0}}
        mock_post.assert_called_once_with(
            "http://43.134.76.215:8000/api/xtdata_call",
            json={"method": "get_full_tick", "args": [["000001.SZ"]], "kwargs": {}}
        )
