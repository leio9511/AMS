import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from scripts.cb_data_loader import fetch_cb_history

@pytest.fixture
def mock_bond_info():
    return pd.DataFrame({
        '债券代码': ['110001', '128001'],
        '发行规模': [10.5, 20.0]
    })

@patch('scripts.cb_data_loader.ak.bond_zh_cov')
@patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis')
@patch('scripts.cb_data_loader.ak.bond_zh_hs_cov_daily')
def test_fetch_cb_history_success_with_high(mock_daily, mock_val, mock_info, mock_bond_info):
    mock_info.return_value = mock_bond_info
    
    # Mock value analysis (premium rate and old close)
    mock_val.return_value = pd.DataFrame({
        '日期': ['2023-01-01', '2023-01-02'],
        '收盘价': [110.0, 112.5],
        '转股溢价率': [5.5, 6.0]
    })
    
    # Mock daily data (OHLC)
    mock_daily.return_value = pd.DataFrame({
        'date': ['2023-01-01', '2023-01-02'],
        'close': [110.1, 112.6],
        'high': [115.0, 118.0]
    })
    
    df = fetch_cb_history(symbols=['110001'])
    
    assert not df.empty
    expected_cols = ['date', 'symbol', 'close', 'high', 'premium_rate', 'outstanding_scale']
    assert all(col in df.columns for col in expected_cols)
    assert len(df) == 2
    assert df.iloc[0]['high'] == 115.0
    # verify merge preference (daily close preferred over value analysis close)
    assert df.iloc[0]['close'] == 110.1 

def test_data_loader_contains_high_column():
    # Use real function with mocked external calls
    with patch('scripts.cb_data_loader.ak.bond_zh_cov') as m_info, \
         patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis') as m_val, \
         patch('scripts.cb_data_loader.ak.bond_zh_hs_cov_daily') as m_daily:
        
        m_info.return_value = pd.DataFrame({'债券代码': ['110001'], '发行规模': [10]})
        m_val.return_value = pd.DataFrame({'日期': ['2023-01-01'], '收盘价': [100], '转股溢价率': [1]})
        m_daily.return_value = pd.DataFrame({'date': ['2023-01-01'], 'close': [100], 'high': [105]})
        
        df = fetch_cb_history(symbols=['110001'])
        assert 'high' in df.columns

def test_high_price_is_numeric():
    with patch('scripts.cb_data_loader.ak.bond_zh_cov') as m_info, \
         patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis') as m_val, \
         patch('scripts.cb_data_loader.ak.bond_zh_hs_cov_daily') as m_daily:
        
        m_info.return_value = pd.DataFrame({'债券代码': ['110001'], '发行规模': [10]})
        m_val.return_value = pd.DataFrame({'日期': ['2023-01-01'], '收盘价': [100], '转股溢价率': [1]})
        m_daily.return_value = pd.DataFrame({'date': ['2023-01-01'], 'close': [100], 'high': [105]})
        
        df = fetch_cb_history(symbols=['110001'])
        assert pd.api.types.is_numeric_dtype(df['high'])
        assert not df['high'].isnull().any()

def test_high_is_greater_than_or_equal_to_close():
    with patch('scripts.cb_data_loader.ak.bond_zh_cov') as m_info, \
         patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis') as m_val, \
         patch('scripts.cb_data_loader.ak.bond_zh_hs_cov_daily') as m_daily:
        
        m_info.return_value = pd.DataFrame({'债券代码': ['110001'], '发行规模': [10]})
        m_val.return_value = pd.DataFrame({'日期': ['2023-01-01'], '收盘价': [100], '转股溢价率': [1]})
        m_daily.return_value = pd.DataFrame({'date': ['2023-01-01'], 'close': [100], 'high': [105]})
        
        df = fetch_cb_history(symbols=['110001'])
        assert (df['high'] >= df['close']).all()

@patch('scripts.cb_data_loader.ak.bond_zh_cov')
@patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis')
@patch('scripts.cb_data_loader.ak.bond_zh_hs_cov_daily')
def test_daily_data_missing_fallback(mock_daily, mock_val, mock_info):
    mock_info.return_value = pd.DataFrame({'债券代码': ['110001'], '发行规模': [10]})
    mock_val.return_value = pd.DataFrame({
        '日期': ['2023-01-01'],
        '收盘价': [110.0],
        '转股溢价率': [5.5]
    })
    # Simulate missing daily data
    mock_daily.return_value = None
    
    df = fetch_cb_history(symbols=['110001'])
    
    assert 'high' in df.columns
    assert df.iloc[0]['high'] == 110.0 # fallback to close
    assert df.iloc[0]['close'] == 110.0
