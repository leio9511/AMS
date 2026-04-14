import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from scripts.cb_data_loader import fetch_cb_history

@patch('scripts.cb_data_loader.ak.bond_zh_cov')
@patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis')
def test_fetch_cb_history_success(mock_val, mock_info):
    # Mock bond info
    mock_info.return_value = pd.DataFrame({
        '债券代码': ['110001'],
        '发行规模': [10.5]
    })
    
    # Mock value analysis
    mock_val.return_value = pd.DataFrame({
        '日期': ['2023-01-01', '2023-01-02'],
        '收盘价': [110.0, 112.5],
        '转股溢价率': [5.5, 6.0]
    })
    
    df = fetch_cb_history(symbols=['110001'])
    
    assert not df.empty
    assert list(df.columns) == ['date', 'symbol', 'close', 'premium_rate', 'outstanding_scale']
    assert len(df) == 2
    assert df.iloc[0]['close'] == 110.0
    assert df.iloc[0]['premium_rate'] == 5.5
    assert df.iloc[0]['outstanding_scale'] == 10.5

@patch('scripts.cb_data_loader.ak.bond_zh_cov')
@patch('scripts.cb_data_loader.ak.bond_zh_cov_value_analysis')
def test_survivorship_bias_handling(mock_val, mock_info):
    # Mock data for 5 bonds, where '110005' is the delisted one
    symbols = ['110001', '110002', '110003', '110004', '110005']
    
    mock_info.return_value = pd.DataFrame({
        '债券代码': symbols,
        '发行规模': [10.0, 20.0, 30.0, 40.0, 50.0]
    })
    
    def side_effect(symbol):
        if symbol == '110005':
            # Delisted halfway: only has data up to 2023-01-02
            return pd.DataFrame({
                '日期': ['2023-01-01', '2023-01-02'],
                '收盘价': [100.0, 95.0],
                '转股溢价率': [2.0, 1.0]
            })
        else:
            # Active bonds have data up to 2023-01-03
            return pd.DataFrame({
                '日期': ['2023-01-01', '2023-01-02', '2023-01-03'],
                '收盘价': [110.0, 112.5, 115.0],
                '转股溢价率': [5.5, 6.0, 6.5]
            })
            
    mock_val.side_effect = side_effect
    
    df = fetch_cb_history(symbols=symbols)
    
    assert not df.empty
    assert len(df) == (4 * 3) + 2  # 4 active bonds * 3 days + 1 delisted * 2 days = 14 rows
    
    # Check that the delisted bond remains up to its delisting date
    delisted_data = df[df['symbol'] == '110005']
    assert len(delisted_data) == 2
    assert delisted_data['date'].max() == pd.to_datetime('2023-01-02')
