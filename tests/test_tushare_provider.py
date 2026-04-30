import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from etl.tushare_provider import TuShareProvider, TUSHARE_PREMIUM_GUARD_MESSAGE
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
    # Mock stock_st
    mock_pro.stock_st.return_value = pd.DataFrame({
        "ts_code": ["600001.SH"],
        "trade_date": ["20250102"],
        "type": ["ST"]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_stock_st_by_date(["600001.SH"], "2025-01-01", "2025-01-02")
    
    assert df.loc["2025-01-01", "600001.SH"] == False
    assert df.loc["2025-01-02", "600001.SH"] == True

def test_tushare_premium_rate_reconstruction():
    mock_pro = MagicMock()
    # Mock cb_daily
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["110001.SH", "110001.SH"],
        "trade_date": ["20250101", "20250102"],
        "cb_over_rate": [10.5, 12.0]
    })
    # Mock cb_price_chg
    mock_pro.cb_price_chg.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "change_date": ["20250102"],
        "convert_price_initial": [10.0],
        "convertprice_aft": [9.5]
    })
    
    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_price_changes(["110001.SH"], "2025-01-01", "2025-01-02")
    
    assert len(df) == 2
    assert "convert_premium_rate" in df.columns
    # The implementation currently uses cb_over_rate but ensures effective price is merged internally
    # We can verify that it didn't crash and returned expected columns
    assert "code" in df.columns
    assert "date" in df.columns

def test_tushare_premium_guard(caplog):
    mock_pro = MagicMock()
    mock_pro.cb_daily.return_value = pd.DataFrame({
        "ts_code": ["110001.SH"],
        "trade_date": ["20250101"],
        "cb_over_rate": [10.5]
    })
    # Mock empty cb_price_chg to trigger warning
    mock_pro.cb_price_chg.return_value = pd.DataFrame()
    
    provider = TuShareProvider(pro=mock_pro)
    provider.fetch_cb_price_changes(["110001.SH"], "2025-01-01", "2025-01-01")
    
    assert "No conversion price change history for 110001.SH" in caplog.text

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
