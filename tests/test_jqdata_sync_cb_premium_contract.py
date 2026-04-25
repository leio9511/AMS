import json
import os
from unittest.mock import patch

import pandas as pd

from etl.jqdata_sync_cb import _build_bond_key_columns, _normalize_premium_source, sync_cb_data


def test_price_ticker_is_normalized_into_bond_code_raw_and_bond_exchange_code():
    df = pd.DataFrame({"ticker": ["110052.XSHG", "123071.XSHE"]})

    normalized = _build_bond_key_columns(df)

    assert normalized["bond_code_raw"].tolist() == ["110052", "123071"]
    assert normalized["bond_exchange_code"].tolist() == ["XSHG", "XSHE"]


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_premium_rate_join_uses_code_exchange_code_and_date_instead_of_full_ticker(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["123071.XSHE"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]},
        index=pd.MultiIndex.from_tuples([(pd.to_datetime("2020-01-02"), "123071.XSHE")], names=["time", "code"]),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame({"code": ["123071.XSHE"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]})
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02"],
            "code": ["123071"],
            "exchange_code": ["XSHE"],
            "convert_premium_rate": [15.5],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
    assert df.loc[0, "premium_rate"] == 0.155


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_premium_rate_join_metrics_are_emitted_with_expected_names(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["123071.XSHE"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]},
        index=pd.MultiIndex.from_tuples([(pd.to_datetime("2020-01-02"), "123071.XSHE")], names=["time", "code"]),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"]))

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame({"code": ["123071.XSHE"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]})
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02"],
            "code": ["123071"],
            "exchange_code": ["XSHE"],
            "convert_premium_rate": [15.5],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    with open("/root/projects/AMS/data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["premium_rate_source_row_count"] == 1
    assert metrics["premium_rate_joined_row_count"] == 1
    assert metrics["premium_rate_join_coverage_ratio"] == 1.0


def test_normalize_premium_source_accepts_split_code_and_exchange_columns():
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02"],
            "code": ["123071"],
            "exchange_code": ["XSHE"],
            "convert_premium_rate": [15.5],
        }
    )

    normalized = _normalize_premium_source(premium)

    assert normalized.loc[0, "bond_code_raw"] == "123071"
    assert normalized.loc[0, "bond_exchange_code"] == "XSHE"
    assert normalized.loc[0, "premium_rate"] == 0.155
