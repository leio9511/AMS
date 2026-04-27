import json
import os
from unittest.mock import patch

import pandas as pd

import etl.jqdata_sync_cb
from etl.jqdata_sync_cb import sync_cb_data


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_records_zero_survivors_for_exclusion_only_window(
    mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk
):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_semantic_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(
        index=["999999.XSHG", "125302.XSHG"]
    )
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000, 1200, 1300],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.to_datetime("2025-01-17"), "999999.XSHG"),
                (pd.to_datetime("2025-01-17"), "125302.XSHG"),
                (pd.to_datetime("2025-01-18"), "125302.XSHG"),
            ],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")
    mock_jqdatasdk.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["125302"],
            "company_code": [None],
            "delist_Date": ["2004-01-01"],
        }
    )

    with patch("os.replace"):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-18")

    tmp_metrics_path = etl.jqdata_sync_cb.METRICS_PATH + ".tmp"
    with open(tmp_metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["row_count"] == 0
    assert metrics["underlying_ticker_nonnull_ratio"] == 0.0
    assert metrics["premium_rate_nonzero_ratio"] == 0.0
    assert metrics["premium_rate_zero_ratio"] == 0.0
    assert metrics["is_st_true_count"] == 0
    assert metrics["is_redeemed_true_count"] == 0
    assert metrics["premium_rate_source_row_count"] == 0
    assert metrics["premium_rate_joined_row_count"] == 0
    assert metrics["premium_rate_join_coverage_ratio"] == 0.0
    assert metrics["is_redeemed_missing_delist_count"] == 0
    assert metrics["filtered_bonds_outside_basic_info_count"] == 1
    assert metrics["filtered_rows_outside_basic_info_count"] == 1
    assert metrics["filtered_bond_codes_outside_basic_info"] == ["999999"]
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 1
    assert metrics["filtered_rows_missing_company_code_legacy_count"] == 2
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == ["125302"]


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_contains_required_premium_and_redemption_contract_fields(
    mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk
):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_semantic_validator_cls.return_value.validate_dataframe.return_value = True
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
            "code": ["123071", "110059"],
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

    assert os.path.exists(etl.jqdata_sync_cb.METRICS_PATH)
    with open(etl.jqdata_sync_cb.METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    queried_raw_codes = mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.call_args.args[0]
    assert queried_raw_codes == ["123071", "110059"]
    assert metrics["premium_rate_source_row_count"] == 2
    assert metrics["premium_rate_joined_row_count"] == 2
    assert metrics["premium_rate_join_coverage_ratio"] == 1.0
    assert metrics["is_redeemed_missing_delist_count"] == 1


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_etl_writes_all_required_metrics(mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_semantic_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["123071.XSHE"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.to_datetime("2020-01-02"), "123071.XSHE"),
            ],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [True]},
        index=pd.to_datetime(["2020-01-02"]),
    )

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {
            "code": ["123071"],
            "company_code": ["000001.XSHE"],
            "delist_Date": ["2020-01-01"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2020-01-02"],
            "code": ["123071"],
            "exchange_code": ["XSHE"],
            "convert_premium_rate": [15.5],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    with patch("os.replace"):
        sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    tmp_metrics_path = etl.jqdata_sync_cb.METRICS_PATH + ".tmp"
    assert os.path.exists(tmp_metrics_path)
    with open(tmp_metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert "row_count" in metrics
    assert "underlying_ticker_nonnull_ratio" in metrics
    assert "premium_rate_nonzero_ratio" in metrics
    assert "premium_rate_zero_ratio" in metrics
    assert "is_st_true_count" in metrics
    assert "is_redeemed_true_count" in metrics
    assert "generated_at" in metrics
    assert "source_lineage" in metrics
    assert metrics["source_lineage"] == "jqdata_sync_cb"
    assert metrics["row_count"] == 1
    assert metrics["is_st_true_count"] == 1
    assert metrics["is_redeemed_true_count"] == 1


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_separates_outside_basic_info_and_missing_company_code_legacy_buckets(
    mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk
):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_semantic_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(
        index=["999999.XSHG", "125302.XSHG", "110059.XSHG"]
    )
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000, 1200, 1500],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.to_datetime("2025-01-17"), "999999.XSHG"),
                (pd.to_datetime("2025-01-17"), "125302.XSHG"),
                (pd.to_datetime("2025-01-17"), "110059.XSHG"),
            ],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]},
        index=pd.to_datetime(["2025-01-17"]),
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {
            "code": ["125302", "110059"],
            "company_code": [None, "000001.XSHE"],
            "delist_Date": ["2004-01-01", "2025-12-31"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2025-01-17"],
            "code": ["110059"],
            "exchange_code": ["XSHG"],
            "convert_premium_rate": [10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    with patch("os.replace"):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    tmp_metrics_path = etl.jqdata_sync_cb.METRICS_PATH + ".tmp"
    with open(tmp_metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["filtered_bonds_outside_basic_info_count"] == 1
    assert metrics["filtered_rows_outside_basic_info_count"] == 1
    assert metrics["filtered_bond_codes_outside_basic_info"] == ["999999"]
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 1
    assert metrics["filtered_rows_missing_company_code_legacy_count"] == 1
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == ["125302"]
    assert "filtered_bond_codes" not in metrics


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_emits_zero_counts_and_empty_lists_for_absent_exclusion_buckets(
    mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk
):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_semantic_validator_cls.return_value.validate_dataframe.return_value = True
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
        index=pd.MultiIndex.from_tuples(
            [(pd.to_datetime("2025-01-17"), "110059.XSHG")],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]},
        index=pd.to_datetime(["2025-01-17"]),
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {
            "code": ["110059"],
            "company_code": ["000001.XSHE"],
            "delist_Date": ["2025-12-31"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2025-01-17"],
            "code": ["110059"],
            "exchange_code": ["XSHG"],
            "convert_premium_rate": [10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    with patch("os.replace"):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    tmp_metrics_path = etl.jqdata_sync_cb.METRICS_PATH + ".tmp"
    with open(tmp_metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["filtered_bonds_outside_basic_info_count"] == 0
    assert metrics["filtered_rows_outside_basic_info_count"] == 0
    assert metrics["filtered_bond_codes_outside_basic_info"] == []
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 0
    assert metrics["filtered_rows_missing_company_code_legacy_count"] == 0
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == []
    assert "filtered_bond_codes" not in metrics


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_builder_emits_zeroed_reason_coded_fields_for_empty_inputs(
    mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk
):
    del mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk

    metrics = etl.jqdata_sync_cb._build_supportability_exclusion_metrics(pd.DataFrame())

    assert metrics == {
        "filtered_bonds_outside_basic_info_count": 0,
        "filtered_rows_outside_basic_info_count": 0,
        "filtered_bond_codes_outside_basic_info": [],
        "filtered_bonds_missing_company_code_legacy_count": 0,
        "filtered_rows_missing_company_code_legacy_count": 0,
        "filtered_bond_codes_missing_company_code_legacy": [],
    }


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
@patch("ams.validators.cb_data_validator.CBDataValidator")
def test_metrics_artifact_code_lists_are_deterministically_sorted(
    mock_validator_cls, mock_semantic_validator_cls, mock_jqdatasdk
):
    mock_validator_cls.return_value.validate_dataframe.return_value = True
    mock_semantic_validator_cls.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(
        index=[
            "999999.XSHG",
            "123000.XSHG",
            "125302.XSHG",
            "110001.XSHG",
            "110059.XSHG",
        ]
    )
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
            "volume": [1000, 1001, 1002, 1003, 1004, 1005, 1006],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.to_datetime("2025-01-17"), "999999.XSHG"),
                (pd.to_datetime("2025-01-18"), "123000.XSHG"),
                (pd.to_datetime("2025-01-18"), "999999.XSHG"),
                (pd.to_datetime("2025-01-17"), "125302.XSHG"),
                (pd.to_datetime("2025-01-18"), "110001.XSHG"),
                (pd.to_datetime("2025-01-18"), "125302.XSHG"),
                (pd.to_datetime("2025-01-17"), "110059.XSHG"),
            ],
            names=["time", "code"],
        ),
    )
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]},
        index=pd.to_datetime(["2025-01-17"]),
    )
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    bonds_info = pd.DataFrame(
        {
            "code": ["125302", "110001", "110059"],
            "company_code": [None, None, "000001.XSHE"],
            "delist_Date": ["2004-01-01", "2003-01-01", "2025-12-31"],
        }
    )
    premium = pd.DataFrame(
        {
            "date": ["2025-01-17"],
            "code": ["110059"],
            "exchange_code": ["XSHG"],
            "convert_premium_rate": [10.0],
        }
    )
    mock_jqdatasdk.bond.run_query.side_effect = [bonds_info, premium]

    with patch("os.replace"):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-18")

    tmp_metrics_path = etl.jqdata_sync_cb.METRICS_PATH + ".tmp"
    with open(tmp_metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["filtered_bonds_outside_basic_info_count"] == 2
    assert metrics["filtered_rows_outside_basic_info_count"] == 3
    assert metrics["filtered_bond_codes_outside_basic_info"] == ["123000", "999999"]
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 2
    assert metrics["filtered_rows_missing_company_code_legacy_count"] == 3
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == ["110001", "125302"]
    assert "filtered_bond_codes" not in metrics
