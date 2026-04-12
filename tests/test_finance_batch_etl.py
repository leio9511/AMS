import json
import math
import os
from unittest.mock import MagicMock, patch
import pytest

from windows_bridge.finance_batch_etl import process_financial_data, sanitize_value

def test_etl_creates_json_with_valid_data():
    mock_xtdata = MagicMock()
    mock_xtdata.get_financial_data.return_value = {
        "000001.SZ": {
            "Capital": [{"total_capital": 1000.0}],
            "Balance": [{"tot_shrhldr_eqy_excl_min_int": 500.0}],
            "Income": [{"net_profit_excl_min_int_inc": 100.0}]
        }
    }
    
    with patch('windows_bridge.finance_batch_etl.xtdata', mock_xtdata):
        result = process_financial_data(["000001.SZ"])
        
        assert result["000001.SZ"]["total_capital"] == 1000.0
        assert result["000001.SZ"]["total_equity"] == 500.0
        assert result["000001.SZ"]["net_profit"] == 100.0

def test_etl_handles_missing_keys_and_nan():
    mock_xtdata = MagicMock()
    mock_xtdata.get_financial_data.return_value = {
        "000002.SZ": {
            "Capital": [{"total_capital": float('nan')}],
            "Balance": [{"total_equity": 300.0}], # tot_shrhldr_eqy_excl_min_int missing
            "Income": [{"net_profit_excl_min_int_inc": None}]
        }
    }
    
    with patch('windows_bridge.finance_batch_etl.xtdata', mock_xtdata):
        result = process_financial_data(["000002.SZ"])
        
        assert result["000002.SZ"]["total_capital"] is None
        assert result["000002.SZ"]["total_equity"] == 300.0
        assert result["000002.SZ"]["net_profit"] is None