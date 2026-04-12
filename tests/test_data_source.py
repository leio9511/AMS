import pytest
import pandas as pd
from scripts.adapter import qmt_to_akshare
from scripts.finance_fetcher import fetch_fundamental_data
from legacy_scripts.pilot_stock_radar import phase1_filter
from unittest.mock import patch, MagicMock

def test_qmt_to_akshare_mapping():
    # Mock QMT get_full_tick response
    mock_qmt_data = {
        "600000.SH": {
            "lastPrice": 10.0,
            "open": 9.9,
            "high": 10.1,
            "low": 9.8,
            "close": 10.0,
            "amount": 1000000.0,
            "volume": 1000,
            "stockName": "浦发银行",
            "lastClose": 9.9,
            "askPrice": [10.1, 10.2, 10.3, 10.4, 10.5],
            "bidPrice": [10.0, 9.9, 9.8, 9.7, 9.6],
            "askVol": [100, 100, 100, 100, 100],
            "bidVol": [100, 100, 100, 100, 100]
        }
    }
    
    df = qmt_to_akshare(mock_qmt_data)
    
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert '代码' in df.columns
    assert df.iloc[0]['代码'] == '600000'
    assert df.iloc[0]['名称'] == '浦发银行'
    assert df.iloc[0]['最新价'] == 10.0
    assert df.iloc[0]['昨收'] == 9.9
    assert abs(df.iloc[0]['涨跌幅'] - (0.1 / 9.9 * 100)) < 0.0001
    assert abs(df.iloc[0]['涨跌额'] - 0.1) < 0.0001
    assert df.iloc[0]['成交量'] == 1000
    assert df.iloc[0]['成交额'] == 1000000.0
    assert df.iloc[0]['最高'] == 10.1
    assert df.iloc[0]['最低'] == 9.8
    assert df.iloc[0]['今开'] == 9.9

@patch('scripts.finance_fetcher.ak.stock_zh_a_spot_em')
def test_fetch_fundamental_data(mock_spot_em):
    # Mock akshare response to avoid network fragility during testing
    mock_df = pd.DataFrame([
        {'代码': '600000', '市盈率-动态': 5.5, '总市值': 100000000},
        {'代码': '600001', '市盈率-动态': 8.2, '总市值': 50000000},
        {'代码': '600002', '市盈率-动态': 15.0, '总市值': 20000000}
    ])
    mock_spot_em.return_value = mock_df

    df = fetch_fundamental_data()
    
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert '代码' in df.columns
    assert '市盈率-动态' in df.columns
    assert '总市值' in df.columns
    
    # Check that PE is not uniformly hardcoded
    pe_values = df['市盈率-动态'].dropna().head(50)
    assert pe_values.nunique() > 1, "PE values are uniform, indicating hardcoded fake data!"

@patch('legacy_scripts.pilot_stock_radar.qmt_client.get_full_tick')
@patch('legacy_scripts.pilot_stock_radar.fetch_fundamental_data')
@patch('legacy_scripts.pilot_stock_radar.ak.index_component_sw')
def test_phase1_filter_integration(mock_sw, mock_finance, mock_qmt):
    # This test verifies that pilot_stock_radar.phase1_filter correctly merges
    # dynamic data from both QMT and Fundamental sources.
    
    mock_qmt.return_value = {
        '600000.SH': {'stockName': 'StockA', 'lastPrice': 10.0, 'lastClose': 10.0},
        '600001.SH': {'stockName': 'StockB', 'lastPrice': 20.0, 'lastClose': 20.0}
    }
    
    mock_finance.return_value = pd.DataFrame([
        {'代码': '600000', '市盈率-动态': 5.0, '总市值': 10000},
        {'代码': '600001', '市盈率-动态': 25.0, '总市值': 20000}
    ])
    
    mock_sw.side_effect = Exception("Skip SW fetch")
    
    # Run phase1_filter
    results, total = phase1_filter()
    
    # Verify results
    # 600000: PE 5.0 -> forecast 4.25 (Pass)
    # 600001: PE 25.0 -> forecast 21.25 (Filtered by MAX_PE=20)
    
    assert any(r['code'] == '600000' for r in results)
    assert not any(r['code'] == '600001' for r in results)
    
    # Verify dynamic PE was used
    stock_a = next(r for r in results if r['code'] == '600000')
    assert stock_a['pe_ttm'] == 5.0
    assert stock_a['pe_forecast'] == 4.25 # 5.0 * 0.85

def test_hardcoded_pe_stub_anti_pattern():
    # Defensive check: Ensure that if we were to re-introduce a hardcoded stub in a DF,
    # the nunique check would catch it.
    df = pd.DataFrame({'市盈率-动态': [15.0] * 10})
    assert df['市盈率-动态'].nunique() == 1
