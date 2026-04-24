import json
import os
import re
from unittest.mock import patch

import pandas as pd
import pytest

from etl.jqdata_sync_cb import (
    LEGACY_REDEMPTION_SOURCE_FATAL,
    REDEMPTION_SOURCE_CONTRACT,
    _raise_legacy_redemption_source_error,
    sync_cb_data,
)


def test_legacy_redemption_source_guard_raises_exact_prd_fatal_message():
    with pytest.raises(RuntimeError, match=re.escape(LEGACY_REDEMPTION_SOURCE_FATAL)):
        _raise_legacy_redemption_source_error()


def test_redemption_source_contract_declares_primary_and_fallback_fields():
    assert REDEMPTION_SOURCE_CONTRACT["source_table"] == "bond.CONBOND_BASIC_INFO"
    assert REDEMPTION_SOURCE_CONTRACT["primary_field"] == "delist_Date"
    assert REDEMPTION_SOURCE_CONTRACT["fallback_informational_fields"] == [
        "maturity_date",
        "last_cash_date",
        "convert_end_date",
    ]
    assert REDEMPTION_SOURCE_CONTRACT["null_primary_behavior"] == "is_redeemed=False"


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_redemption_source_contract_keeps_null_delist_behavior_deterministic(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        },
        index=pd.MultiIndex.from_tuples([(pd.to_datetime("2020-01-02"), "110059.XSHG")], names=["time", "code"]),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"])
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {
            "code": ["110059.XSHG"],
            "company_code": ["000001.XSHE"],
            "delist_Date": [None],
            "maturity_date": ["2030-01-01"],
            "last_cash_date": ["2020-01-01"],
            "convert_end_date": ["2029-12-31"],
        }
    )
    premium = pd.DataFrame(
        {"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    df = pd.read_csv("data/cb_history_factors.csv")
    assert bool(df.loc[0, "is_redeemed"]) is False
    with open("data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["is_redeemed_missing_delist_count"] == 1


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_is_redeemed_becomes_true_on_and_after_delist_date(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 99.0],
            "close": [100.5, 100.5],
            "volume": [1000, 1000],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.to_datetime("2020-01-01"), "110059.XSHG"),
                (pd.to_datetime("2020-01-02"), "110059.XSHG"),
            ],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False, False]}, index=pd.to_datetime(["2020-01-01", "2020-01-02"])
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2020-01-02"]}
    )
    premium = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02"],
            "code": ["110059", "110059"],
            "exchange_code": ["XSHG", "XSHG"],
            "convert_premium_rate": [10.0, 10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data(start_date="2020-01-01", end_date="2020-01-02")

    df = pd.read_csv("data/cb_history_factors.csv")
    assert bool(df.loc[df["date"] == "2020-01-01", "is_redeemed"].iloc[0]) is False
    assert bool(df.loc[df["date"] == "2020-01-02", "is_redeemed"].iloc[0]) is True


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_null_delist_date_forces_false_and_increments_missing_delist_metric(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        },
        index=pd.MultiIndex.from_tuples([(pd.to_datetime("2020-01-02"), "110059.XSHG")], names=["time", "code"]),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"])
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": [None]}
    )
    premium = pd.DataFrame(
        {"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    df = pd.read_csv("data/cb_history_factors.csv")
    assert bool(df.loc[0, "is_redeemed"]) is False
    with open("data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["is_redeemed_missing_delist_count"] == 1


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_etl_never_queries_finance_ccb_call_after_contract_repair(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        },
        index=pd.MultiIndex.from_tuples([(pd.to_datetime("2020-01-02"), "110059.XSHG")], names=["time", "code"]),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"])
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {"code": ["110059.XSHG"], "company_code": ["000001.XSHE"], "delist_Date": ["2020-01-02"]}
    )
    premium = pd.DataFrame(
        {"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    df = pd.read_csv("data/cb_history_factors.csv")
    assert bool(df.loc[0, "is_redeemed"]) is True
