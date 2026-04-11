import pytest
import pandas as pd
from unittest.mock import MagicMock
from scripts.qmt_data_adapter import QMTDataAdapter, FIELD_MAPPING

def test_get_stock_zh_a_spot_em_schema_matching():
    mock_client = MagicMock()
    mock_client.get_full_tick.return_value = [
        {
            "stock_code": "000001.SZ",
            "stock_name": "平安银行",
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
    ]
    
    adapter = QMTDataAdapter(mock_client)
    df = adapter.get_stock_zh_a_spot_em()
    
    assert isinstance(df, pd.DataFrame)
    
    # Check all mapped columns exist
    for expected_col in FIELD_MAPPING.values():
        assert expected_col in df.columns
        
    assert df.iloc[0]["代码"] == "000001.SZ"
    assert df.iloc[0]["名称"] == "平安银行"

def test_adapter_handles_empty_response():
    mock_client = MagicMock()
    mock_client.get_full_tick.return_value = []
    
    adapter = QMTDataAdapter(mock_client)
    df = adapter.get_stock_zh_a_spot_em()
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    
    for expected_col in FIELD_MAPPING.values():
        assert expected_col in df.columns
