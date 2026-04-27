import etl.jqdata_sync_cb
import json
import os
from unittest.mock import patch

import pandas as pd
import pytest

from etl.jqdata_sync_cb import SUPPORTABILITY_REGRESSION_ERROR, sync_cb_data


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
        pd.DataFrame({"code": ["110059"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
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

    assert os.path.exists(etl.jqdata_sync_cb.DATA_PATH)
    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
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
                "code": ["123071", "110059"],
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

    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
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
        pd.DataFrame({"code": ["110059"], "company_code": ["000001.XSHE"], "delist_Date": ["2020-01-01"]}),
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

    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
    assert bool(df.loc[0, "is_redeemed"]) is True
    assert df.loc[0, "underlying_ticker"] == "000001.XSHE"


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_sync_cb_data_raises_when_normalized_underlying_mapping_is_missing(mock_semantic_validator, mock_jqdatasdk):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        # Bond is IN CONBOND_BASIC_INFO but company_code is NaN → mapping will fail
        pd.DataFrame({"code": ["110059"], "company_code": [None], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}),
    ]
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

    with pytest.raises(ValueError, match="Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"):
        sync_cb_data()


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb._build_underlying_mapping", return_value={"110059.XSHG": "000001.XSHE"})
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_full_ticker_cannot_be_used_as_underlying_map_key(
    mock_semantic_validator, mock_jqdatasdk, _mock_build_underlying_mapping
):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}),
    ]
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

    with pytest.raises(ValueError, match="Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"):
        sync_cb_data()


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_bonds_outside_basic_info_are_filtered_not_blocking(mock_semantic_validator, mock_jqdatasdk):
    """Verify bonds outside CONBOND_BASIC_INFO (like 125302) are silently filtered
    instead of raising ValueError, while bonds inside basic_info still proceed."""
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    # get_all_securities returns two bonds: 125302.XSHG (outside basic_info) + 110059.XSHG (inside)
    mock_df_bonds = pd.DataFrame(
        {"code": ["125302.XSHG", "110059.XSHG"], "end_date": [pd.NaT, pd.NaT]}
    )
    mock_df_bonds.index = ["125302.XSHG", "110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    # CONBOND_BASIC_INFO only has 110059 — NOT 125302
    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame(
            {"code": ["110059"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}
        ),
        pd.DataFrame(
            {
                "date": ["2020-01-02"],
                "code": ["110059"],
                "exchange_code": ["XSHG"],
                "convert_premium_rate": [10.0],
            }
        ),
    ]

    # get_price returns data for BOTH bonds — the filter must drop 125302 rows
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2020-01-02", "2020-01-02"],
            "code": ["125302.XSHG", "110059.XSHG"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        }
    ).set_index(["time", "code"])

    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]}, index=pd.to_datetime(["2020-01-02"])
    )
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdatasdk.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
    mock_jqdatasdk.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")

    # Must NOT raise ValueError
    sync_cb_data()

    # Output CSV exists and contains ONLY 110059.XSHG
    assert os.path.exists(etl.jqdata_sync_cb.DATA_PATH)
    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
    assert len(df) == 1
    assert set(df["ticker"].unique()) == {"110059.XSHG"}
    assert "125302.XSHG" not in df["ticker"].values


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_sync_cb_data_real_window_known_legacy_case_is_accounted_for_in_reason_coded_metrics(
    mock_semantic_validator, mock_jqdatasdk
):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame(
        {"code": ["125302.XSHG", "110059.XSHG"], "end_date": [pd.NaT, pd.NaT]}
    )
    mock_df_bonds.index = ["125302.XSHG", "110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame(
            {
                "code": ["125302", "110059"],
                "company_code": [None, "000001.XSHE"],
                "delist_Date": ["2004-01-01", "2025-12-31"],
            }
        ),
        pd.DataFrame(
            {
                "date": ["2025-01-17"],
                "code": ["110059"],
                "exchange_code": ["XSHG"],
                "convert_premium_rate": [10.0],
            }
        ),
    ]

    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2025-01-17", "2025-01-17"],
            "code": ["125302.XSHG", "110059.XSHG"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]}, index=pd.to_datetime(["2025-01-17"])
    )
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
    assert set(df["ticker"].unique()) == {"110059.XSHG"}
    with open(etl.jqdata_sync_cb.METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 1
    assert metrics["filtered_rows_missing_company_code_legacy_count"] == 1
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == ["125302"]
    assert metrics["filtered_bonds_outside_basic_info_count"] == 0
    assert metrics["filtered_bond_codes_outside_basic_info"] == []


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_sync_cb_data_reason_coded_metrics_survive_empty_price_rows(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None
    mock_jqdatasdk.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["125302", "110059"],
            "company_code": [None, "000001.XSHE"],
            "delist_Date": ["2004-01-01", "2025-12-31"],
        }
    )
    mock_jqdatasdk.get_all_securities.return_value = pd.DataFrame(index=["125302.XSHG", "110059.XSHG"])
    mock_jqdatasdk.get_price.return_value = pd.DataFrame()

    with pytest.raises(ValueError, match="No price data found for the given range"):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    metrics = etl.jqdata_sync_cb._build_supportability_exclusion_metrics(pd.DataFrame())
    assert metrics["filtered_bonds_outside_basic_info_count"] == 0
    assert metrics["filtered_rows_outside_basic_info_count"] == 0
    assert metrics["filtered_bond_codes_outside_basic_info"] == []
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 0
    assert metrics["filtered_rows_missing_company_code_legacy_count"] == 0
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == []


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_sync_cb_data_exclusion_only_window_does_not_raise_false_missing_is_st_failure(
    mock_jqdatasdk,
):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame(
        {"code": ["125302.XSHG", "999999.XSHG"], "end_date": [pd.NaT, pd.NaT]}
    )
    mock_df_bonds.index = ["125302.XSHG", "999999.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["125302"],
            "company_code": [None],
            "delist_Date": ["2004-01-01"],
        }
    )
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2025-01-17", "2025-01-17"],
            "code": ["125302.XSHG", "999999.XSHG"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        }
    ).set_index(["time", "code"])

    existing_canonical = pd.DataFrame(
        {
            "ticker": ["110059.XSHG"],
            "date": ["2025-01-16"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "premium_rate": [0.1],
            "double_low": [110.5],
            "underlying_ticker": ["000001.XSHE"],
            "is_st": [False],
            "is_redeemed": [False],
        }
    )
    existing_canonical.to_csv(etl.jqdata_sync_cb.DATA_PATH, index=False)

    sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
    assert df.to_dict(orient="records") == existing_canonical.to_dict(orient="records")
    with open(etl.jqdata_sync_cb.METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["row_count"] == 0
    assert metrics["filtered_bond_codes_outside_basic_info"] == ["999999"]
    assert metrics["filtered_bond_codes_missing_company_code_legacy"] == ["125302"]


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_sync_cb_data_exclusion_only_window_skips_downstream_premium_and_is_st_queries(
    mock_semantic_validator, mock_jqdatasdk
):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame(
        {"code": ["125302.XSHG", "999999.XSHG"], "end_date": [pd.NaT, pd.NaT]}
    )
    mock_df_bonds.index = ["125302.XSHG", "999999.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["125302"],
            "company_code": [None],
            "delist_Date": ["2004-01-01"],
        }
    )
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2025-01-17", "2025-01-17"],
            "code": ["125302.XSHG", "999999.XSHG"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        }
    ).set_index(["time", "code"])

    sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    assert mock_jqdatasdk.bond.run_query.call_count == 1
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.assert_not_called()
    mock_jqdatasdk.get_extras.assert_not_called()


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_sync_cb_data_still_hard_fails_when_zero_survivors_are_not_legacy_allowed(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["110059"],
            "company_code": [None],
            "delist_Date": ["2025-12-31"],
        }
    )
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2025-01-17"],
            "code": ["110059.XSHG"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    ).set_index(["time", "code"])

    with pytest.raises(ValueError, match=SUPPORTABILITY_REGRESSION_ERROR):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_sync_cb_data_hard_fails_for_null_company_code_without_legacy_justification(mock_jqdatasdk):
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame(
            {"code": ["110059"], "company_code": [None], "delist_Date": [None]}
        ),
        pd.DataFrame(
            {
                "date": ["2025-01-17"],
                "code": ["110059"],
                "exchange_code": ["XSHG"],
                "convert_premium_rate": [10.0],
            }
        ),
    ]
    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2025-01-17"],
            "code": ["110059.XSHG"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    ).set_index(["time", "code"])

    with pytest.raises(ValueError, match=SUPPORTABILITY_REGRESSION_ERROR):
        sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
@patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
def test_sync_cb_data_keeps_outside_basic_info_filtering_and_supportable_rows_green(
    mock_semantic_validator, mock_jqdatasdk
):
    mock_semantic_validator.return_value.validate_dataframe.return_value = True
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame(
        {"code": ["999999.XSHG", "110059.XSHG"], "end_date": [pd.NaT, pd.NaT]}
    )
    mock_df_bonds.index = ["999999.XSHG", "110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame(
            {"code": ["110059"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}
        ),
        pd.DataFrame(
            {
                "date": ["2025-01-17"],
                "code": ["110059"],
                "exchange_code": ["XSHG"],
                "convert_premium_rate": [10.0],
            }
        ),
    ]

    mock_jqdatasdk.get_price.return_value = pd.DataFrame(
        {
            "time": ["2025-01-17", "2025-01-17"],
            "code": ["999999.XSHG", "110059.XSHG"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
        }
    ).set_index(["time", "code"])
    mock_jqdatasdk.get_extras.return_value = pd.DataFrame(
        {"000001.XSHE": [False]}, index=pd.to_datetime(["2025-01-17"])
    )
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdatasdk.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

    sync_cb_data(start_date="2025-01-17", end_date="2025-01-17")

    df = pd.read_csv(etl.jqdata_sync_cb.DATA_PATH)
    assert len(df) == 1
    assert set(df["ticker"].unique()) == {"110059.XSHG"}
    with open(etl.jqdata_sync_cb.METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["filtered_bond_codes_outside_basic_info"] == ["999999"]
    assert metrics["filtered_bonds_missing_company_code_legacy_count"] == 0


@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch("etl.jqdata_sync_cb.jqdatasdk")
def test_fail_fast_still_fires_for_bonds_in_basic_info_with_missing_mapping(mock_jqdatasdk):
    """Verify that when a bond EXISTS in CONBOND_BASIC_INFO but its company_code
    is NaN (no underlying_ticker mapping possible), the fail-fast gate STILL fires
    with the updated error message."""
    mock_jqdatasdk.auth.return_value = None

    mock_df_bonds = pd.DataFrame({"code": ["110059.XSHG"], "end_date": [pd.NaT]})
    mock_df_bonds.index = ["110059.XSHG"]
    mock_jqdatasdk.get_all_securities.return_value = mock_df_bonds

    # Bond IS in CONBOND_BASIC_INFO but company_code is NaN → mapping will fail
    mock_jqdatasdk.bond.run_query.side_effect = [
        pd.DataFrame(
            {"code": ["110059"], "company_code": [None], "delist_Date": ["2025-12-31"]}
        ),
        pd.DataFrame(
            {
                "date": ["2020-01-02"],
                "code": ["110059"],
                "exchange_code": ["XSHG"],
                "convert_premium_rate": [10.0],
            }
        ),
    ]

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

    # Fail-fast must fire with the NEW error message
    with pytest.raises(ValueError, match="Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"):
        sync_cb_data()
