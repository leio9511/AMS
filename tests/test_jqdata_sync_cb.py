import json
import os
from unittest.mock import patch

import pandas as pd
import pytest

from etl.jqdata_sync_cb import sync_cb_data


@patch.dict(os.environ, {}, clear=True)
def test_jqdata_auth_failure():
    with pytest.raises(ValueError, match="Missing JQDATA_USER or JQDATA_PWD environment variables"):
        sync_cb_data()


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_jqdata_successful_sync(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}),
    ]

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2020-01-02"],
            "code": ["110059.XSHG"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    sync_cb_data()

    assert os.path.exists("data/cb_history_factors.csv")
    df = pd.read_csv("data/cb_history_factors.csv")
    expected_cols = {
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "premium_rate",
        "double_low",
        "underlying_ticker",
        "is_st",
        "is_redeemed",
    }
    assert expected_cols.issubset(set(df.columns))
    assert df.loc[0, "underlying_ticker"] == "000001.XSHE"


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_underlying_contract_regression_keeps_dataset_valid(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}),
    ]

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2020-01-02"],
            "code": ["110059.XSHG"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    sync_cb_data()

    df = pd.read_csv("data/cb_history_factors.csv")
    assert df.loc[0, "underlying_ticker"] == "000001.XSHE"
    assert df.loc[0, "premium_rate"] == 0.1
    assert df.loc[0, "is_st"] in (False, 0)


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_premium_rate_contract_change_keeps_validator_path_green(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["123071.XSHE"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["123071.XSHE"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["123071.XSHE"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["123071"], "exchange_code": ["XSHE"], "convert_premium_rate": [15.5]}),
    ]

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2020-01-02"],
            "code": ["123071.XSHE"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    sync_cb_data()

    df = pd.read_csv("data/cb_history_factors.csv")
    assert df.loc[0, "premium_rate"] == 0.155
    with open("data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["premium_rate_source_row_count"] == 1
    assert metrics["premium_rate_joined_row_count"] == 1
    assert metrics["premium_rate_join_coverage_ratio"] == 1.0


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_redemption_contract_change_remains_validator_compatible(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2020-01-01"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}),
    ]

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2020-01-02"],
            "code": ["110059.XSHG"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data()

    df = pd.read_csv("data/cb_history_factors.csv")
    assert bool(df.loc[0, "is_redeemed"]) is True
    with open("data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["is_redeemed_missing_delist_count"] == 0
