import json
import os
from unittest.mock import patch

import pandas as pd

from etl.jqdata_sync_cb import METRICS_PATH, sync_cb_data


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_contains_required_premium_and_redemption_contract_fields(mock_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["123071.XSHE", "110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.to_datetime("2020-01-02"), "123071.XSHE"),
                (pd.to_datetime("2020-01-02"), "110059.XSHG"),
            ],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False], "000002.XSHG": [False]},
        index=pd.to_datetime(["2020-01-02"]),
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {
            "code": ["123071.XSHE", "110059.XSHG"],
            "company_code": ["000001.XSHE", "000002.XSHG"],
            "delist_Date": [None, "2020-01-01"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02", "2020-01-02"],
            "code": ["123071", "110059"],
            "exchange_code": ["XSHE", "XSHG"],
            "convert_premium_rate": [15.5, 10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    assert os.path.exists(METRICS_PATH)
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["premium_rate_source_row_count"] == 2
    assert metrics["premium_rate_joined_row_count"] == 2
    assert metrics["premium_rate_join_coverage_ratio"] == 1.0
    assert metrics["is_redeemed_missing_delist_count"] == 1
