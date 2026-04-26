import etl.jqdata_sync_cb
import os
import re
from unittest.mock import patch

import pandas as pd
import pytest

from etl.jqdata_sync_cb import (
    LEGACY_UNDERLYING_SOURCE_FATAL,
    _build_underlying_mapping,
    _raise_legacy_underlying_source_error,
    sync_cb_data,
)


def test_legacy_underlying_source_guard_raises_exact_prd_fatal_message():
    with pytest.raises(RuntimeError, match=re.escape(LEGACY_UNDERLYING_SOURCE_FATAL)):
        _raise_legacy_underlying_source_error()


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_underlying_ticker_is_mapped_from_basic_info_company_code(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    bonds_info = pd.DataFrame(
        {
            "code": ["110059"],
            "company_code": ["600000.XSHG"],
            "delist_Date": ["2025-12-31"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02"],
            "code": ["110059"],
            "exchange_code": ["XSHG"],
            "convert_premium_rate": [10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        },
        index=pd.MultiIndex.from_tuples(
            [(pd.to_datetime("2020-01-02"), "110059.XSHG")], names=["time", "code"]
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"600000.XSHG": [False]}, index=pd.to_datetime(["2020-01-02"])
    )

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
    assert df.loc[0, "underlying_ticker"] == "600000.XSHG"


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_underlying_ticker_path_does_not_use_full_ticker_as_mapping_key(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    bonds_info = pd.DataFrame(
        {
            "code": ["110059"],
            "company_code": ["600000.XSHG"],
            "delist_Date": ["2025-12-31"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02"],
            "code": ["110059"],
            "exchange_code": ["XSHG"],
            "convert_premium_rate": [10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        },
        index=pd.MultiIndex.from_tuples(
            [(pd.to_datetime("2020-01-02"), "110059.XSHG")], names=["time", "code"]
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"600000.XSHG": [False]}, index=pd.to_datetime(["2020-01-02"])
    )

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdatasdk.get_security_info.side_effect = AssertionError(
        "legacy get_security_info(ticker).parent path must not be used"
    )

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    queried_raw_codes = mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.call_args.args[0]
    assert queried_raw_codes == ["110059"]
    assert not mock_jqdatasdk.get_security_info.called


def test_build_underlying_mapping_preserves_raw_basic_info_code_keys():
    df_bonds_info = pd.DataFrame(
        {
            "code": ["110059", "123071"],
            "company_code": ["600000.XSHG", "000001.XSHE"],
        }
    )

    mapping = _build_underlying_mapping(df_bonds_info)

    assert mapping == {
        "110059": "600000.XSHG",
        "123071": "000001.XSHE",
    }


def test_build_underlying_mapping_uses_company_code_column():
    df_bonds_info = pd.DataFrame(
        {
            "code": ["123456", "123457"],
            "company_code": ["600000.XSHG", "000001.XSHE"],
        }
    )

    mapping = _build_underlying_mapping(df_bonds_info)

    assert mapping == {
        "123456": "600000.XSHG",
        "123457": "000001.XSHE",
    }
