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
    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"]})
    # Setting index to mimic get_all_securities behavior if script uses it
    mock_df_bonds.index = ["110059.XSHG"]
    
    mock_jqdatasdk.finance.run_query.return_value = mock_df_bonds
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds
    
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