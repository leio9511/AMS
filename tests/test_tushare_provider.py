import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from etl.tushare_provider import TuShareProvider
from etl.cb_provider_base import DataProviderQuotaError, DataProviderAuthError, DataProviderError

def test_tushare_cb_basic_mapping():
    mock_pro = MagicMock()
    mock_pro.cb_basic.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "stk_code": ["600001.SH"],
        "delist_date": ["20251231"]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_basic()
    
    assert "code" in df.columns
    assert "company_code" in df.columns
    assert "delist_Date" in df.columns
    assert df.iloc[0]["code"] == "110001.SH"
    assert df.iloc[0]["company_code"] == "600001.SH"
    # delist_Date is converted in pipeline usually, but provider just renames
    assert df.iloc[0]["delist_Date"] == "20251231"

def test_tushare_is_st_logic():
    mock_pro = MagicMock()
    # Mock trade calendar
    mock_pro.trade_cal.return_value = pd.DataFrame({
        "cal_date": ["20250101", "20250102"]
    })
    # Mock stock_st to be called by trade_date
    def mock_stock_st(trade_date=None, ts_code=None, start_date=None, end_date=None):
        if trade_date == "20250102":
            return pd.DataFrame({
                "ts_code": ["600001.SH"],
                "trade_date": ["20250102"],
                "type": ["ST"]
            })
        return pd.DataFrame()
    
    mock_pro.stock_st.side_effect = mock_stock_st
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_stock_st_by_date(["600001.SH"], "2025-01-01", "2025-01-02")
    
    assert df.loc["2025-01-01", "600001.SH"] == False
    assert df.loc["2025-01-02", "600001.SH"] == True
    # Verify it was called with trade_date
    mock_pro.stock_st.assert_any_call(trade_date="20250101")
    mock_pro.stock_st.assert_any_call(trade_date="20250102")

def test_tushare_daily_volume_mapping():
    mock_pro = MagicMock()
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250120"]})
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["127076.SZ"],
        "trade_date": ["20250120"],
        "close": [100.0],
        "vol": [5000.0]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_daily(["127076.SZ"], "2025-01-20", "2025-01-20")
    
    assert "volume" in df.columns
    assert df.iloc[0]["volume"] == 5000.0
    assert "vol" not in df.columns

def test_tushare_premium_reconstruction_correctness():
    mock_pro = MagicMock()
    # Mock trade_cal for fetch_trade_calendar
    mock_pro.trade_cal.return_value = pd.DataFrame({
        "cal_date": ["20250102"]
    })
    # Mock cb_basic for mapping
    mock_pro.cb_basic.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "stk_code": ["600001.SH"],
        "delist_date": ["20300101"]
    })
    # Mock cb_daily: bond price = 120
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "trade_date": ["20250102"],
        "close": [120.0],
        "vol": [1000.0]
    })
    # Mock stock daily: stock price = 10
    mock_pro.daily.return_value = pd.DataFrame({
        "ts_code": ["600001.SH"],
        "trade_date": ["20250102"],
        "close": [10.0]
    })
    # Mock cb_price_chg: conv price = 9.5
    mock_pro.cb_price_chg.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "change_date": ["20250101"],
        "convert_price_initial": [10.0],
        "convertprice_aft": [9.5]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_price_changes(["110001.SH"], "2025-01-02", "2025-01-02")
    
    assert len(df) == 1
    assert "convert_premium_rate" in df.columns
    
    # Math:
    # effective_conv_price = 9.5 (since 20250101)
    # bond_close = 120
    # stock_close = 10
    # premium = (120 / ((100 / 9.5) * 10) - 1) * 100
    
    expected_premium = (120.0 / ((100.0 / 9.5) * 10.0) - 1.0) * 100.0
    assert pytest.approx(df.iloc[0]["convert_premium_rate"], 0.0001) == expected_premium

def test_tushare_premium_fails_closed():
    mock_pro = MagicMock()
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250102"]})
    mock_pro.cb_basic.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "stk_code": ["600001.SH"],
        "delist_date": ["20300101"]
    })
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "trade_date": ["20250102"],
        "close": [120.0],
        "vol": [1000.0]
    })
    # Mock empty stock daily
    mock_pro.daily.return_value = pd.DataFrame()
    # Mock cb_price_chg
    mock_pro.cb_price_chg.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "change_date": ["20250101"],
        "convert_price_initial": [10.0],
        "convertprice_aft": [9.5]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_price_changes(["110001.SH"], "2025-01-02", "2025-01-02")
    
    # premium_rate should be NaN because stock_close is missing
    assert pd.isna(df.iloc[0]["convert_premium_rate"])

def test_tushare_premium_fails_closed_missing_conv_price():
    mock_pro = MagicMock()
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250102"]})
    mock_pro.cb_basic.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "stk_code": ["600001.SH"],
        "delist_date": ["20300101"]
    })
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "trade_date": ["20250102"],
        "close": [120.0],
        "vol": [1000.0]
    })
    mock_pro.daily.return_value = pd.DataFrame({
        "ts_code": ["600001.SH"],
        "trade_date": ["20250102"],
        "close": [10.0]
    })
    # Mock empty cb_price_chg
    mock_pro.cb_price_chg.return_value = pd.DataFrame()
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_price_changes(["110001.SH"], "2025-01-02", "2025-01-02")
    
    # premium_rate should be NaN because effective_conv_price is missing
    assert pd.isna(df.iloc[0]["convert_premium_rate"])

def test_tushare_premium_uses_historical_conv_price():
    mock_pro = MagicMock()
    # Mock two days
    mock_pro.trade_cal.return_value = pd.DataFrame({
        "cal_date": ["20250102", "20250110"]
    })
    mock_pro.cb_basic.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "stk_code": ["600001.SH"],
        "delist_date": ["20300101"]
    })
    # Mock cb_daily: bond price = 120 on both days
    mock_pro.cb_daily.side_effect = [
        pd.DataFrame({"ts_code": ["110001.SH"], "trade_date": ["20250102"], "close": [120.0], "vol": [1000.0]}),
        pd.DataFrame({"ts_code": ["110001.SH"], "trade_date": ["20250110"], "close": [120.0], "vol": [1000.0]})
    ]
    # Mock stock daily: stock price = 10 on both days
    mock_pro.daily.return_value = pd.DataFrame({
        "ts_code": ["600001.SH", "600001.SH"],
        "trade_date": ["20250102", "20250110"],
        "close": [10.0, 10.0]
    })
    # Mock cb_price_chg: conv price changes from 9.5 to 10.5 on 20250105
    mock_pro.cb_price_chg.return_value = pd.DataFrame({
        "ts_code": ["110001.SH", "110001.SH"],
        "change_date": ["20250101", "20250105"],
        "convert_price_initial": [9.0, 9.5],
        "convertprice_aft": [9.5, 10.5]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_price_changes(["110001.SH"], "2025-01-02", "2025-01-10")
    
    df = df.sort_values("date")
    assert len(df) == 2
    
    # Day 1 (2025-01-02): effective_conv_price should be 9.5
    premium1 = df.iloc[0]["convert_premium_rate"]
    expected1 = (120.0 / ((100.0 / 9.5) * 10.0) - 1.0) * 100.0
    assert pytest.approx(premium1, 0.0001) == expected1
    
    # Day 2 (2025-01-10): effective_conv_price should be 10.5
    premium2 = df.iloc[1]["convert_premium_rate"]
    expected2 = (120.0 / ((100.0 / 10.5) * 10.0) - 1.0) * 100.0
    assert pytest.approx(premium2, 0.0001) == expected2



def test_tushare_quota_error():
    mock_pro = MagicMock()
    mock_pro.cb_basic.side_effect = Exception("抱歉，您每分钟最多访问该接口次数限制")
    
    provider = TuShareProvider(pro=mock_pro)
    with pytest.raises(DataProviderQuotaError):
        provider.fetch_cb_basic()

def test_tushare_auth_error():
    mock_pro = MagicMock()
    mock_pro.cb_basic.side_effect = Exception("抱歉，您输入的TOKEN无效")
    
    provider = TuShareProvider(pro=mock_pro)
    with pytest.raises(DataProviderAuthError):
        provider.fetch_cb_basic()

def test_tushare_cb_daily_query_strategy():
    mock_pro = MagicMock()
    # Setup: Mock trade_cal to return two trading days
    mock_pro.trade_cal.return_value = pd.DataFrame({
        "cal_date": ["20250120", "20250121"]
    })
    
    # Setup: Mock cb_daily for each day
    def mock_cb_daily(trade_date=None):
        if trade_date == "20250120":
            return pd.DataFrame({
                "ts_code": ["127076.SZ", "110001.SH"],
                "trade_date": ["20250120", "20250120"],
                "close": [100.0, 110.0]
            })
        elif trade_date == "20250121":
            return pd.DataFrame({
                "ts_code": ["127076.SZ", "999999.SH"],
                "trade_date": ["20250121", "20250121"],
                "close": [101.0, 120.0]
            })
        return pd.DataFrame()
    
    mock_pro.cb_daily.side_effect = mock_cb_daily
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_daily(["127076.SZ"], "2025-01-20", "2025-01-21")
    
    # Assertions
    assert mock_pro.cb_daily.call_count == 2
    mock_pro.cb_daily.assert_any_call(trade_date="20250120")
    mock_pro.cb_daily.assert_any_call(trade_date="20250121")
    
    # Verify result contains only for "127076.SZ"
    assert len(df) == 2
    assert all(df.index.get_level_values("code") == "127076.SZ")
    
    # Verify index and formatting
    assert isinstance(df.index, pd.MultiIndex)
    assert "2025-01-20" in df.index.get_level_values("time")
    assert "2025-01-21" in df.index.get_level_values("time")

def test_tushare_cb_daily_empty_range():
    mock_pro = MagicMock()
    # Mock trade_cal to return empty dataframe with expected columns
    mock_pro.trade_cal.return_value = pd.DataFrame(columns=["cal_date"])
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_daily(["127076.SZ"], "2025-01-25", "2025-01-26")
    
    assert df.empty

def test_tushare_full_ticker_contract_compliance():
    """
    Verify that provider methods strictly use the provided tickers 
    without attempting to guess suffixes or handle raw codes.
    """
    mock_pro = MagicMock()
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250120"]})
    # Mock cb_daily returning mixed tickers
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["127076.SZ", "110001.SH", "123456.SZ"],
        "trade_date": ["20250120", "20250120", "20250120"],
        "close": [100.0, 110.0, 120.0],
        "vol": [1000, 2000, 3000]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    # If we pass a list of full tickers, it should only return those.
    df = provider.fetch_cb_daily(["127076.SZ", "110001.SH"], "2025-01-20", "2025-01-20")
    
    assert len(df) == 2
    assert "127076.SZ" in df.index.get_level_values("code")
    assert "110001.SH" in df.index.get_level_values("code")
    assert "123456.SZ" not in df.index.get_level_values("code")
    
    # Verify that it didn't do any complex parsing, just a straight 'isin' filter
    # which is the current implementation.

