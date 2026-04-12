import pytest
from unittest.mock import patch, MagicMock
from scripts.qmt_client import QMTClient
import httpx

def test_get_fundamentals_success():
    client = QMTClient()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"status": "success", "data": {"510300.SH": {"iopv": 4.4, "pe": 15.0}}}
    
    with patch("httpx.get", return_value=mock_resp):
        res = client.get_fundamentals()
        assert res == {"status": "success", "data": {"510300.SH": {"iopv": 4.4, "pe": 15.0}}}

def test_get_fundamentals_connection_error():
    client = QMTClient()
    
    with patch("httpx.get", side_effect=httpx.RequestError("Connection failed")):
        res = client.get_fundamentals()
        assert res.get("status") == "error"
        assert "Connection failed" in res.get("message")
