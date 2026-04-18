import os
import pytest
from unittest.mock import patch, MagicMock
from scripts.jqdata_sync_cb import sync_cb_data

@patch.dict(os.environ, {}, clear=True)
def test_jqdata_auth_failure():
    with pytest.raises(ValueError, match="Missing JQDATA_USER or JQDATA_PWD environment variables"):
        sync_cb_data()

@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch('scripts.jqdata_sync_cb.jqdatasdk')
def test_jqdata_successful_sync(mock_jqdatasdk):
    # Mock auth success
    mock_jqdatasdk.auth.return_value = None
    
    # Mock bond list (for get_all_securities and run_query)
    import pandas as pd
    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    # Setting index to mimic get_all_securities behavior if script uses it
    mock_df_bonds.index = ["110059.XSHG"]
    
    mock_jqdatasdk.finance.run_query.return_value = mock_df_bonds
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds
    
    # Mock security info
    mock_info = MagicMock()
    mock_info.parent = "000001.XSHE"
    mock_jqdatasdk.get_security_info.return_value = mock_info
    
    # Mock bond.run_query
    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({'code': ["110059.XSHG"], 'delist_Date': ['2025-12-31']}), # df_bonds_info
        pd.DataFrame({'date': ['2020-01-02'], 'code': ["110059.XSHG"], 'convert_premium_rate': [10.0]}) # df_premium
    ]
    
    # Mock get_extras (is_st)
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(['2020-01-02']))

    # Mock query attributes
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    
    # Mock get_price
    mock_df_price = pd.DataFrame({
        "time": ["2020-01-02"],
        "code": ["110059.XSHG"],
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [1000]
    }).set_index(["time", "code"])
    mock_jqdatasdk.get_price.return_value = mock_df_price
    
    # Run sync
    sync_cb_data()
    
    # Check if csv created
    assert os.path.exists("data/cb_history_factors.csv")
    
    # Check columns
    df = pd.read_csv("data/cb_history_factors.csv")
    expected_cols = {"ticker", "date", "open", "high", "low", "close", "volume", "premium_rate", "double_low", "underlying_ticker", "is_st", "is_redeemed"}
    assert expected_cols.issubset(set(df.columns))
@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch('scripts.jqdata_sync_cb.jqdatasdk')
def test_fetch_ccb_call_data_success(mock_jqdatasdk):
    import pandas as pd
    mock_jqdatasdk.auth.return_value = None
    
    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds
    
    mock_info = MagicMock()
    mock_info.parent = "000001.XSHE"
    mock_jqdatasdk.get_security_info.return_value = mock_info
    
    # Mock bond.run_query
    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({'code': ["110059.XSHG"], 'delist_Date': ['2025-12-31']}), # df_bonds_info
        pd.DataFrame({'date': ['2020-01-02'], 'code': ["110059.XSHG"], 'convert_premium_rate': [10.0]}) # df_premium
    ]
    
    # Mock finance.run_query for CCB_CALL
    mock_df_call = pd.DataFrame({
        "code": ["110059.XSHG"],
        "pub_date": ["2020-01-01"],
        "delisting_date": ["2020-01-05"]
    })
    mock_jqdatasdk.finance.run_query.return_value = mock_df_call

    # Mock query attributes
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    
    # Mock finance query attributes
    mock_jqdatasdk.finance.CCB_CALL.code.in_.return_value = True
    
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(['2020-01-02']))
    
    # Mock get_price
    mock_df_price = pd.DataFrame({
        "time": ["2020-01-02"],
        "code": ["110059.XSHG"],
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [1000]
    }).set_index(["time", "code"])
    mock_jqdatasdk.get_price.return_value = mock_df_price
    
    sync_cb_data()
    
    df = pd.read_csv("data/cb_history_factors.csv")
    assert df.loc[0, "is_redeemed"] == True

@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch('scripts.jqdata_sync_cb.jqdatasdk')
def test_fetch_ccb_call_data_empty(mock_jqdatasdk):
    import pandas as pd
    mock_jqdatasdk.auth.return_value = None
    
    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds
    
    mock_info = MagicMock()
    mock_info.parent = "000001.XSHE"
    mock_jqdatasdk.get_security_info.return_value = mock_info
    
    # Mock bond.run_query
    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({'code': ["110059.XSHG"], 'delist_Date': ['2025-12-31']}), # df_bonds_info
        pd.DataFrame({'date': ['2020-01-02'], 'code': ["110059.XSHG"], 'convert_premium_rate': [10.0]}) # df_premium
    ]
    
    # Mock finance.run_query for CCB_CALL to return empty DataFrame
    mock_df_call = pd.DataFrame()
    mock_jqdatasdk.finance.run_query.return_value = mock_df_call

    # Mock query attributes
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    
    # Mock finance query attributes
    mock_jqdatasdk.finance.CCB_CALL.code.in_.return_value = True
    
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(['2020-01-02']))
    
    # Mock get_price
    mock_df_price = pd.DataFrame({
        "time": ["2020-01-02"],
        "code": ["110059.XSHG"],
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [1000]
    }).set_index(["time", "code"])
    mock_jqdatasdk.get_price.return_value = mock_df_price
    
    sync_cb_data()
    
    df = pd.read_csv("data/cb_history_factors.csv")
    assert df.loc[0, "is_redeemed"] == False

