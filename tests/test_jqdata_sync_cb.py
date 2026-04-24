import os
import pytest
from unittest.mock import MagicMock, patch

from etl.jqdata_sync_cb import sync_cb_data


@patch.dict(os.environ, {}, clear=True)
def test_jqdata_auth_failure():
    with pytest.raises(ValueError, match="Missing JQDATA_USER or JQDATA_PWD environment variables"):
        sync_cb_data()


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_jqdata_successful_sync(mock_jqdatasdk):
    import pandas as pd

    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]

    mock_jqdatasdk.finance.run_query.return_value = mock_df_bonds
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059.XSHG"], "convert_premium_rate": [10.0]}),
    ]

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    mock_df_price = pd.DataFrame(
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
    mock_jqdatasdk.get_price.return_value = mock_df_price
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
    import pandas as pd

    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059.XSHG"], "convert_premium_rate": [10.0]}),
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
def test_fetch_ccb_call_data_success(mock_jqdatasdk):
    import pandas as pd

    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059.XSHG"], "convert_premium_rate": [10.0]}),
    ]

    mock_df_call = pd.DataFrame(
        {"code": ["110059.XSHG"], "pub_date": ["2020-01-01"], "delisting_date": ["2020-01-05"]}
    )
    mock_jqdatasdk.finance.run_query.return_value = mock_df_call

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    mock_jqdatasdk.finance.CCB_CALL.code.in_.return_value = True

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))

    mock_df_price = pd.DataFrame(
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
    mock_jqdatasdk.get_price.return_value = mock_df_price
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    sync_cb_data()

    df = pd.read_csv("data/cb_history_factors.csv")
    assert df.loc[0, "is_redeemed"] == True


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_fetch_ccb_call_data_empty(mock_jqdatasdk):
    import pandas as pd

    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059.XSHG"], "convert_premium_rate": [10.0]}),
    ]

    mock_jqdatasdk.finance.run_query.return_value = pd.DataFrame()

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    mock_jqdatasdk.finance.CCB_CALL.code.in_.return_value = True

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))

    mock_df_price = pd.DataFrame(
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
    mock_jqdatasdk.get_price.return_value = mock_df_price
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    sync_cb_data()

    df = pd.read_csv("data/cb_history_factors.csv")
    assert df.loc[0, "is_redeemed"] == False
