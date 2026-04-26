import etl.jqdata_sync_cb
import json
import os
import pandas as pd
import pytest
import shutil
from unittest.mock import MagicMock, patch

# Prepend project root to imports if necessary, or assume installed in environment
# Since it's a monorepo, we might need to adjust sys.path
import sys
sys.path.append("/root/projects/AMS")

from etl.jqdata_sync_cb import sync_cb_data

@pytest.fixture
def mock_jqdata(monkeypatch):
    monkeypatch.setenv("JQDATA_USER", "test_user")
    monkeypatch.setenv("JQDATA_PWD", "test_pwd")
    
    # Pre-mock JQDataClient and tables to prevent real auth and attribute access attempts
    mock_basic_info = MagicMock()
    mock_daily_convert = MagicMock()
    # Mock date/code attributes to support >= and .in_
    mock_daily_convert.date.__ge__.return_value = MagicMock()
    mock_daily_convert.date.__le__.return_value = MagicMock()
    mock_daily_convert.code.in_.return_value = MagicMock()

    with patch("jqdatasdk.client.JQDataClient.instance", return_value=MagicMock()), \
         patch("jqdatasdk.auth") as mock_auth, \
         patch("jqdatasdk.get_all_securities") as mock_get_all, \
         patch("jqdatasdk.get_price") as mock_get_price, \
         patch("jqdatasdk.get_security_info") as mock_get_info, \
         patch("jqdatasdk.bond.run_query") as mock_run_query, \
         patch("jqdatasdk.get_extras") as mock_get_extras, \
         patch("jqdatasdk.query") as mock_query, \
         patch("jqdatasdk.bond.CONBOND_BASIC_INFO", mock_basic_info, create=True), \
         patch("jqdatasdk.bond.CONBOND_DAILY_CONVERT", mock_daily_convert, create=True):
        
        # Setup basic info
        mock_get_all.return_value = pd.DataFrame(index=["123456.SH"])
        
        # Price data
        price_df = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]
        }, index=pd.to_datetime(["2025-01-06"]))
        price_df.index.name = "time"
        # get_price returns a MultiIndex if multiple tickers are passed
        # But for one ticker it returns a DataFrame with DatetimeIndex
        # sync_cb_data expects 'time' and 'code' columns after reset_index
        price_df_reset = price_df.reset_index()
        price_df_reset["code"] = "123456.SH"
        mock_get_price.return_value = price_df_reset.set_index(["time", "code"])

        # Security info
        mock_info = MagicMock()
        mock_info.parent = "600000.SH"
        mock_get_info.return_value = mock_info

        # run_query for bonds info
        bonds_info = pd.DataFrame({
            "code": ["123456"], "company_code": ["600000.SH"], "delist_Date": ["2026-01-01"]
        })
        
        # run_query for premium rate
        premium_df = pd.DataFrame({
            "date": ["2025-01-06"], "code": ["123456"], "exchange_code": ["SH"], "convert_premium_rate": [15.5]
        })
        
        mock_run_query.side_effect = [bonds_info, premium_df]

        # ST status
        st_df = pd.DataFrame({
            "600000.SH": [False]
        }, index=pd.to_datetime(["2025-01-06"]))
        mock_get_extras.return_value = st_df

        yield {
            "auth": mock_auth,
            "get_price": mock_get_price,
            "run_query": mock_run_query
        }

def test_backup_creation(mock_jqdata, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_file = data_dir / "cb_history_factors.csv"
    csv_file.write_text("old,data")
    
    # Change working directory to tmp_path for the test
    with patch("os.makedirs"), \
         patch("os.path.dirname", return_value=str(data_dir)), \
         patch("os.path.exists", side_effect=lambda p: os.path.exists(p) if not p.startswith("data/") else os.path.exists(os.path.join(tmp_path, p))), \
         patch("os.replace") as mock_replace:
        
        # We need to be careful with paths in the script
        # The script uses "data/..." relative paths
        # Let's mock the path checks and copy
        
        # Mocking os.path.exists to return True for the specific file
        def side_effect_exists(path):
            if path == etl.jqdata_sync_cb.DATA_PATH:
                return True
            return False

        with patch("os.path.exists", side_effect=side_effect_exists):
             try:
                 sync_cb_data()
             except:
                 pass # We expect it might fail later due to other paths
             
             mock_replace.assert_any_call(etl.jqdata_sync_cb.DATA_PATH, f"{etl.jqdata_sync_cb.DATA_PATH}.bak")

def test_validator_integration(mock_jqdata, tmp_path):
    # This test checks if CBDataValidator is called
    with patch("ams.validators.cb_data_validator.CBDataValidator") as mock_validator_cls:
        mock_validator = mock_validator_cls.return_value
        mock_validator.validate_dataframe.return_value = True
        
        with patch("pandas.DataFrame.to_csv"), \
             patch("pandas.read_csv"), \
             patch("os.replace"), \
             patch("os.makedirs"), \
             patch("os.path.exists", return_value=False):
            
            sync_cb_data()
            mock_validator.validate_dataframe.assert_called()

def test_atomic_write_success(mock_jqdata, tmp_path):
    with patch("os.replace") as mock_replace, \
         patch("ams.validators.cb_data_validator.CBDataValidator") as mock_validator_cls, \
         patch("os.makedirs"), \
         patch("os.path.exists", return_value=False), \
         patch("pandas.DataFrame.to_csv"), \
         patch("pandas.read_csv") as mock_read_csv:
        
        mock_validator = mock_validator_cls.return_value
        mock_validator.validate_dataframe.return_value = True
        mock_read_csv.return_value = pd.DataFrame({
            "ticker": ["123456.SH"], "date": ["2025-01-06"], "close": [100.5],
            "premium_rate": [0.155], "is_st": [False], "is_redeemed": [False]
        })
        
        sync_cb_data()
        mock_replace.assert_any_call(f"{etl.jqdata_sync_cb.DATA_PATH}.tmp", etl.jqdata_sync_cb.DATA_PATH)


def test_sync_cb_data_writes_metrics_artifact_without_breaking_atomic_csv_flow(mock_jqdata, tmp_path):
    with patch("os.replace") as mock_replace, \
         patch("ams.validators.cb_data_validator.CBDataValidator") as mock_validator_cls, \
         patch("os.makedirs"), \
         patch("os.path.exists", return_value=False), \
         patch("pandas.DataFrame.to_csv"), \
         patch("pandas.read_csv") as mock_read_csv, \
         patch("builtins.open", create=True) as mock_open:

        mock_validator = mock_validator_cls.return_value
        mock_validator.validate_dataframe.return_value = True
        mock_read_csv.return_value = pd.DataFrame({
            "ticker": ["123456.SH"], "date": ["2025-01-06"], "close": [100.5],
            "premium_rate": [0.155], "is_st": [False], "is_redeemed": [True]
        })

        sync_cb_data()

        mock_replace.assert_any_call(f"{etl.jqdata_sync_cb.DATA_PATH}.tmp", etl.jqdata_sync_cb.DATA_PATH)
        opened_paths = [call.args[0] for call in mock_open.call_args_list if call.args]
        assert f"{etl.jqdata_sync_cb.METRICS_PATH}.tmp" in opened_paths

def test_validation_interception(mock_jqdata, tmp_path):
    with patch("os.replace") as mock_replace, \
         patch("ams.validators.cb_data_validator.CBDataValidator") as mock_validator_cls, \
         patch("os.makedirs"), \
         patch("os.path.exists", return_value=True), \
         patch("pandas.DataFrame.to_csv"), \
         patch("pandas.read_csv"), \
         patch("os.remove") as mock_remove:
        
        import pytest
        mock_validator = mock_validator_cls.return_value
        mock_validator.validate_dataframe.return_value = False # Force failure
        
        with pytest.raises(SystemExit):
            sync_cb_data()
        mock_replace.assert_not_called()
