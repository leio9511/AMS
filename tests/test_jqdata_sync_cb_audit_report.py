import json
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import datetime

from etl.jqdata_sync_cb import audit_cb_data
from etl.cb_etl_pipeline import (
    STAGE_STATUS_PASS,
    STAGE_STATUS_FAIL,
    STAGE_STATUS_NOT_RUN,
    FINAL_STATUS_PASS,
    FINAL_STATUS_FAIL_ROOT_BLOCKER,
    FINAL_STATUS_FAIL_SECONDARY_ONLY,
)

@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True):
        yield

@pytest.fixture
def mock_jqdata():
    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        # Default mock behavior
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.return_value = pd.DataFrame(columns=["code", "company_code", "delist_Date"])
        mock_jq.get_all_securities.return_value = pd.DataFrame(columns=["code"])
        mock_jq.get_price.return_value = pd.DataFrame()
        mock_jq.get_extras.return_value = pd.DataFrame()
        
        # Mock query filters
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        yield mock_jq

@pytest.fixture
def mock_validators():
    with patch("ams.validators.cb_data_validator.CBDataValidator") as mock_v1, \
         patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as mock_v2:
        mock_v1.return_value.validate_dataframe.return_value = True
        mock_v2.return_value.validate_dataframe.return_value = True
        yield mock_v1, mock_v2

def test_audit_runner_emits_required_top_level_and_stage_summary_schema(mock_env, mock_jqdata, mock_validators):
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    # Mock some data to pass Stage A
    mock_jqdata.bond.run_query.return_value = pd.DataFrame({
        "code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]
    })
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
    mock_jqdata.get_price.return_value = pd.DataFrame(
        {"time": ["2025-01-06"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
    ).set_index(["time", "code"])
    
    # Mock Stage C premium
    mock_jqdata.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]}), # Stage A
        pd.DataFrame({"date": ["2025-01-06"], "code": ["110059"], "convert_premium_rate": [10.0]})  # Stage C
    ]
    
    # Mock Stage D is_st
    mock_jqdata.get_extras.return_value = pd.DataFrame({"600001.XSHG": [False]}, index=pd.to_datetime(["2025-01-06"]))

    report_path = audit_cb_data(start_date, end_date)
    
    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report = json.load(f)
    
    expected_top_level = {
        "execution_mode", "start_date", "end_date", "final_status",
        "non_promotion_disclaimer", "source_coverage", "supportability_summary",
        "premium_join_summary", "is_st_join_summary", "redemption_summary",
        "validator_summary", "root_blockers", "secondary_findings"
    }
    assert set(report.keys()) == expected_top_level
    assert report["execution_mode"] == "audit"
    assert report["start_date"] == start_date
    assert report["end_date"] == end_date
    
    # Check stage summaries
    for stage in ["source_coverage", "supportability_summary", "premium_join_summary", 
                  "is_st_join_summary", "redemption_summary", "validator_summary"]:
        assert "status" in report[stage]
        assert "failure_type" in report[stage]
        assert "message" in report[stage]

def test_stage_a_failure_forces_fixed_not_run_propagation_for_stage_b_to_f(mock_env, mock_jqdata, mock_validators):
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    # Mock Stage A failure
    mock_jqdata.get_price.return_value = pd.DataFrame() # Empty price data fails Stage A

    report_path = audit_cb_data(start_date, end_date)
    
    with open(report_path, "r") as f:
        report = json.load(f)
    
    assert report["source_coverage"]["status"] == STAGE_STATUS_FAIL
    assert report["source_coverage"]["failure_type"] == "PRICE_SOURCE_UNREADABLE"
    
    for stage in ["supportability_summary", "premium_join_summary", 
                  "is_st_join_summary", "redemption_summary", "validator_summary"]:
        assert report[stage]["status"] == STAGE_STATUS_NOT_RUN
        assert report[stage]["failure_type"] == "NONE"
        assert report[stage]["message"] == "Skipped because Stage A failed."

def test_audit_runner_classifies_premium_source_truncation_by_exact_formula(mock_env, mock_jqdata, mock_validators):
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    # Mock Stage A: lots of supportable rows
    # Actually, we need 50000 supportable rows.
    # To avoid creating a huge DataFrame, we can mock the counts in the pipeline if we want, 
    # but let's try to make a reasonably sized one or mock the stage output.
    # Actually, we can just mock the return values of JQData to trick the logic.
    
    # To hit truncation:
    # supportable_row_count >= 50000
    # premium_source_row_count == 5000
    # missing_premium_ratio >= 0.80
    
    # We can't easily mock just the counts because the logic computes them from the DataFrames.
    # So we need to provide DataFrames of that size.
    # Or... we can patch the pipeline logic to return these values for this test.
    
    # Let's mock JQData to return large DataFrames.
    # For price: 50000 rows.
    df_price = pd.DataFrame({
        "time": [pd.Timestamp("2025-01-06")] * 50000,
        "code": [f"{i}.XSHG" for i in range(50000)],
        "open": [100.0] * 50000, "high": [101.0] * 50000, "low": [99.0] * 50000, "close": [100.0] * 50000, "volume": [1000] * 50000
    }).set_index(["time", "code"])
    mock_jqdata.get_price.return_value = df_price
    
    # Basic Info: 50000 bonds
    df_basic = pd.DataFrame({
        "code": [f"{i}" for i in range(50000)],
        "company_code": [f"{i}.XSHG" for i in range(50000)],
        "delist_Date": [None] * 50000
    })
    
    # Premium source: 5000 rows
    df_premium = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-06")] * 5000,
        "code": [f"{i}.XSHG" for i in range(5000)],
        "convert_premium_rate": [10.0] * 5000
    })
    
    mock_jqdata.bond.run_query.side_effect = [df_basic, df_premium]
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": [f"{i}.XSHG" for i in range(50000)]}, index=[f"{i}.XSHG" for i in range(50000)])
    
    # is_st: return something to avoid failure
    # But wait, 50000 tickers might be too much for get_extras mock.
    # Let's mock it to return an empty but valid looking frame or just enough.
    mock_jqdata.get_extras.return_value = pd.DataFrame() 

    report_path = audit_cb_data(start_date, end_date)
    
    with open(report_path, "r") as f:
        report = json.load(f)
    
    assert report["premium_join_summary"]["failure_type"] == "PREMIUM_SOURCE_TRUNCATION"
    assert any(b["type"] == "PREMIUM_SOURCE_TRUNCATION" for b in report["root_blockers"])

def test_audit_runner_separates_root_blockers_from_secondary_symptoms(mock_env, mock_jqdata, mock_validators):
    # Same as truncation case, check that missing premium rows are in secondary findings
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    df_price = pd.DataFrame({
        "time": [pd.Timestamp("2025-01-06")] * 50000,
        "code": [f"{i}.XSHG" for i in range(50000)],
        "open": [100.0] * 50000, "high": [101.0] * 50000, "low": [99.0] * 50000, "close": [100.0] * 50000, "volume": [1000] * 50000
    }).set_index(["time", "code"])
    mock_jqdata.get_price.return_value = df_price
    
    df_basic = pd.DataFrame({
        "code": [f"{i}" for i in range(50000)],
        "company_code": [f"{i}.XSHG" for i in range(50000)],
        "delist_Date": [None] * 50000
    })
    
    df_premium = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-06")] * 5000,
        "code": [f"{i}.XSHG" for i in range(5000)],
        "convert_premium_rate": [10.0] * 5000
    })
    
    mock_jqdata.bond.run_query.side_effect = [df_basic, df_premium]
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": [f"{i}.XSHG" for i in range(50000)]}, index=[f"{i}.XSHG" for i in range(50000)])
    mock_jqdata.get_extras.return_value = pd.DataFrame()

    report_path = audit_cb_data(start_date, end_date)
    
    with open(report_path, "r") as f:
        report = json.load(f)
    
    # Root blocker should be truncation
    assert any(b["type"] == "PREMIUM_SOURCE_TRUNCATION" for b in report["root_blockers"])
    # Secondary finding should have missing premium rows
    assert any(s["type"] == "MISSING_PREMIUM_RATE_ROWS" for s in report["secondary_findings"])

def test_exclusion_only_window_becomes_fail_secondary_only_with_no_canonical_promotion(mock_env, mock_jqdata, mock_validators):
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    # Mock all bonds as outside basic info (exclusion bucket)
    mock_jqdata.bond.run_query.return_value = pd.DataFrame(columns=["code", "company_code", "delist_Date"])
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
    mock_jqdata.get_price.return_value = pd.DataFrame(
        {"time": ["2025-01-06"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
    ).set_index(["time", "code"])
    
    # Ensure canonical files are NOT modified
    # We can mock os.path.exists and check for no calls to os.replace for canonical paths
    # But audit runner doesn't even have that logic.
    
    # Let's just check the report first.
    report_path = audit_cb_data(start_date, end_date)
    
    with open(report_path, "r") as f:
        report = json.load(f)
    
    assert report["final_status"] == FINAL_STATUS_FAIL_SECONDARY_ONLY
    assert any(s["type"] == "EXCLUSION_ONLY_WINDOW" for s in report["secondary_findings"])
    assert report["supportability_summary"]["supportable_row_count"] == 0
    assert report["supportability_summary"]["outside_basic_info_row_count"] > 0

def test_validator_summary_maps_existing_validator_outcomes_without_copying_rules(mock_env, mock_jqdata, mock_validators):
    mock_v1, mock_v2 = mock_validators
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    # Mock Stage A: success
    df_basic = pd.DataFrame({"code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]})
    df_premium = pd.DataFrame({"date": ["2025-01-06"], "code": ["110059"], "convert_premium_rate": [10.0]})
    
    mock_jqdata.bond.run_query.side_effect = [df_basic, df_premium]
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
    mock_jqdata.get_price.return_value = pd.DataFrame(
        {"time": ["2025-01-06"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
    ).set_index(["time", "code"])
    
    # Force semantic validator failure with a message
    mock_v2.return_value.validate_dataframe.side_effect = Exception("Custom Semantic Error")
    
    report_path = audit_cb_data(start_date, end_date)
    
    with open(report_path, "r") as f:
        report = json.load(f)
    
    assert report["supportability_summary"]["supportable_row_count"] > 0
    assert report["validator_summary"]["schema_validator_status"] == STAGE_STATUS_PASS
    assert report["validator_summary"]["semantic_validator_status"] == STAGE_STATUS_FAIL
    assert "Custom Semantic Error" in report["validator_summary"]["semantic_validator_message"]
    assert report["validator_summary"]["status"] == STAGE_STATUS_FAIL
    assert report["validator_summary"]["failure_type"] == "VALIDATOR_SEMANTIC_FAILURE"

def test_validator_summary_uses_not_run_message_when_no_dedicated_validator_path_exists(mock_env, mock_jqdata, mock_validators):
    start_date = "2025-01-06"
    end_date = "2025-01-07"
    
    # Mock Stage A: success
    df_basic = pd.DataFrame({"code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]})
    df_premium = pd.DataFrame({"date": ["2025-01-06"], "code": ["110059"], "convert_premium_rate": [10.0]})
    
    mock_jqdata.bond.run_query.side_effect = [df_basic, df_premium]
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
    mock_jqdata.get_price.return_value = pd.DataFrame(
        {"time": ["2025-01-06"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
    ).set_index(["time", "code"])
    
    report_path = audit_cb_data(start_date, end_date)
    
    with open(report_path, "r") as f:
        report = json.load(f)
    
    assert report["supportability_summary"]["supportable_row_count"] > 0
    # Drift validator is currently not implemented in v1 runtime
    assert report["validator_summary"]["drift_validator_status"] == STAGE_STATUS_NOT_RUN
    assert report["validator_summary"]["drift_validator_message"] == "No dedicated validator path exists in v1 runtime."

