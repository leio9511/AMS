import pytest
import pandas as pd
from unittest.mock import MagicMock
from scripts.qmt_data_adapter import QMTDataAdapter, FIELD_MAPPING

def test_get_stock_zh_a_spot_em_schema_matching():
    mock_client = MagicMock()
    mock_client.get_full_tick.return_value = {
        "000001.SZ": {
            "stockName": "平安银行",
            "lastPrice": 10.5,
            "open": 10.4,
            "high": 10.6,
            "low": 10.3,
            "preClose": 10.4,
            "volume": 1000000,
            "amount": 10500000,
            "changePercent": 0.96,
            "extra_field": "ignore_me"
        }
    }
    
    adapter = QMTDataAdapter(mock_client)
    df = adapter.get_stock_zh_a_spot_em()
    
    assert isinstance(df, pd.DataFrame)
    
    # Check all mapped columns exist
    for expected_col in FIELD_MAPPING.values():
        assert expected_col in df.columns
        
    assert df.iloc[0]["代码"] == "000001"
    assert df.iloc[0]["名称"] == "平安银行"

def test_adapter_handles_empty_response():
    mock_client = MagicMock()
    mock_client.get_full_tick.return_value = {}
    
    adapter = QMTDataAdapter(mock_client)
    df = adapter.get_stock_zh_a_spot_em()
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    
    for expected_col in FIELD_MAPPING.values():
        assert expected_col in df.columns

def test_get_stock_zh_a_spot_em_filters_hk():
    mock_client = MagicMock()
    mock_client.get_full_tick.return_value = {
        "000001.SZ": {"lastPrice": 10.5},
        "00700.HK": {"lastPrice": 300.0}
    }
    
    adapter = QMTDataAdapter(mock_client)
    df = adapter.get_stock_zh_a_spot_em()
    
    assert len(df) == 1
    # Test Case 1: assert that get_stock_zh_a_spot_em() returns a DataFrame that DOES NOT contain any stock codes ending with .HK
    # Since stock_code strips the suffix, we test the mock logic indirectly. To be rigorous, we can check original codes aren't passed,
    # but the PR instruction specifically asks to assert on the DataFrame. 
    # If the original code was somehow kept in '代码', it shouldn't end with .HK. 
    codes = df["代码"].astype(str).tolist()
    assert not any(c.endswith('.HK') for c in codes)
    assert "000001" in codes
    assert "00700" not in codes

def test_get_stock_hk_spot_em():
    mock_client = MagicMock()
    mock_client.get_full_tick.return_value = {
        "000001.SZ": {"lastPrice": 10.5},
        "00700.HK": {"lastPrice": 300.0, "stockName": "Tencent"}
    }
    
    adapter = QMTDataAdapter(mock_client)
    df = adapter.get_stock_hk_spot_em()
    
    # Test Case 2: assert that get_stock_hk_spot_em() returns a DataFrame populated ONLY with stock codes ending with .HK 
    # and correctly maps columns according to FIELD_MAPPING.
    # Note: adapter strips .HK suffix, so "00700" is returned, but we check length to verify filtering.
    assert len(df) == 1
    codes = df["代码"].astype(str).tolist()
    assert "00700" in codes
    assert "000001" not in codes
    
    # Assert FIELD_MAPPING correctly mapped
    for expected_col in FIELD_MAPPING.values():
        assert expected_col in df.columns
