import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from legacy_scripts.pilot_stock_radar import phase1_filter

@patch('legacy_scripts.pilot_stock_radar.qmt_adapter')
@patch('legacy_scripts.pilot_stock_radar.fetch_fundamental_data')
@patch('legacy_scripts.pilot_stock_radar.ak')
def test_radar_execution_with_mocked_adapter(mock_ak, mock_fetch, mock_adapter):
    # Mock sw_mapping logic in ak
    mock_index_comp = pd.DataFrame([{"证券代码": "000001.SZ"}])
    mock_ak.index_component_sw.return_value = mock_index_comp
    
    # Mock adapter response
    mock_df = pd.DataFrame([{
        "代码": "000001.SZ",
        "名称": "平安银行",
        "最新价": 10.5,
        "今开": 10.4,
        "最高": 10.6,
        "最低": 10.3,
        "昨收": 10.4,
        "成交量": 1000000,
        "成交额": 10500000,
        "涨跌幅": 0.96,
        "年初至今涨跌幅": -15.0,
        "市盈率-动态": 6.0
    }])
    mock_adapter.get_stock_zh_a_spot_em.return_value = mock_df
    
    # Mock finance data
    mock_finance = pd.DataFrame([{
        "代码": "000001.SZ"
    }])
    mock_fetch.return_value = mock_finance
    
    results, scanned = phase1_filter()
    
    assert scanned == 1
    assert len(results) == 1
    assert results[0]["code"] == "000001.SZ"
    assert results[0]["pe_forecast"] == 6.0 * 0.85

@patch('legacy_scripts.pilot_stock_radar.qmt_adapter')
@patch('legacy_scripts.pilot_stock_radar.fetch_fundamental_data')
@patch('legacy_scripts.pilot_stock_radar.ak')
def test_radar_avoids_akshare_for_spot_data(mock_ak, mock_fetch, mock_adapter):
    # Mock dependencies
    mock_adapter.get_stock_zh_a_spot_em.return_value = pd.DataFrame()
    mock_fetch.return_value = pd.DataFrame()
    
    phase1_filter()
    
    # Ensure ak.stock_zh_a_spot_em is NOT called
    mock_ak.stock_zh_a_spot_em.assert_not_called()
    # But QMT adapter is called
    mock_adapter.get_stock_zh_a_spot_em.assert_called_once()
