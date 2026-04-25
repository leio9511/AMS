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
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_jqdata_successful_sync(mock_semantic_validator, mock_jqdatasdk):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
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
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data()

    assert os.path.exists("/root/projects/AMS/data/cb_history_factors.csv")
    df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
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
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_integrated_source_contract_repairs_keep_dataset_generation_green(mock_semantic_validator, mock_jqdatasdk):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["123071.XSHE", "110059.XSHG"], "end_date": [pd.NaT, pd.NaT]})
    mock_df_bonds.index = ["123071.XSHE", "110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame(
            {
                "code": ["123071.XSHE", "110059.XSHG"],
                "company_code": ["000001.XSHE", "000002.XSHG"],
                "delist_Date": [None, "2020-01-01"],
            }
        ),
        pd.DataFrame(
            {
                "date": ["2020-01-02", "2020-01-02"],
                "code": ["123071", "110059"],
                "exchange_code": ["XSHE", "XSHG"],
                "convert_premium_rate": [15.5, 10.0],
            }
        ),
    ]

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False], "000002.XSHG": [False]},
        index=pd.to_datetime(["2020-01-02"]),
    )
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2020-01-02", "2020-01-02"],
            "code": ["123071.XSHE", "110059.XSHG"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data()

    df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
    assert len(df) == 2
    assert set(df["premium_rate"].round(3).tolist()) == {0.155, 0.1}
    assert bool(df.loc[df["ticker"] == "123071.XSHE", "is_redeemed"].iloc[0]) is False
    assert bool(df.loc[df["ticker"] == "110059.XSHG", "is_redeemed"].iloc[0]) is True


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_integrated_source_contract_flow_rejects_legacy_underlying_and_redemption_paths(mock_semantic_validator, mock_jqdatasdk):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
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

    df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
    assert bool(df.loc[0, "is_redeemed"]) is True
    assert df.loc[0, "underlying_ticker"] == "000001.XSHE"
