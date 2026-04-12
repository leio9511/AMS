import json
import pytest
from unittest.mock import patch, Mock
import requests
from scripts.query_spread import get_spread

@patch('scripts.query_spread.requests.get')
def test_query_spread_success(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"current_price": 1.600, "iopv": 1.500}
    mock_get.return_value = mock_response

    result = get_spread("159501.SZ")
    
    assert result["ticker"] == "159501.SZ"
    assert result["current_price"] == 1.600
    assert result["iopv"] == 1.500
    assert result["premium_pct"] == 6.67

@patch('scripts.query_spread.requests.get')
def test_query_spread_bridge_failure(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    
    result = get_spread("159501.SZ")
    
    assert "error" in result
    assert "QMT bridge failure" in result["error"]
