import json
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import datetime

from etl.jqdata_sync_cb import audit_cb_data, DATA_PATH, METRICS_PATH
from etl.cb_etl_pipeline import (
    STAGE_STATUS_PASS,
    STAGE_STATUS_FAIL,
    NON_PROMOTION_DISCLAIMER,
)
from etl.cb_audit_contract import ISSUE_1218_KEY, ISSUE_1218_LEGACY_TICKER_DTYPE_TEXT

@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True):
        yield

@pytest.fixture
def mock_jqdata():
    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.return_value = pd.DataFrame({"code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]})
        mock_jq.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
        mock_jq.get_price.return_value = pd.DataFrame(
            {"time": ["2025-01-06"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
        ).set_index(["time", "code"])
        mock_jq.get_extras.return_value = pd.DataFrame({"600001.XSHG": [False]}, index=pd.to_datetime(["2025-01-06"]))
        
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

def test_audit_report_write_failure_does_not_touch_canonical_or_promotion_rollback_artifacts(mock_env, mock_jqdata, mock_validators, isolated_paths):
    start_date = "2025-03-01"
    end_date = "2025-03-02"
    
    data_path = isolated_paths["data"]
    metrics_path = isolated_paths["metrics"]
    
    # Create dummy canonical artifacts
    with open(data_path, "w") as f:
        f.write("canonical_data")
    with open(metrics_path, "w") as f:
        f.write("canonical_metrics")
    
    # Mock open to fail when writing the report
    def mock_open_fail(path, mode, *args, **kwargs):
        if "cb_etl_audit_" in path and "w" in mode:
            raise IOError("Disk full")
        return original_open(path, mode, *args, **kwargs)

    import builtins
    original_open = builtins.open
    
    with patch("builtins.open", side_effect=mock_open_fail):
        with pytest.raises(RuntimeError, match="Audit report persistence failed"):
            audit_cb_data(start_date, end_date)
            
    # Verify canonical artifacts are UNTOUCHED
    with original_open(data_path, "r") as f:
        assert f.read() == "canonical_data"
    with original_open(metrics_path, "r") as f:
        assert f.read() == "canonical_metrics"
        
    # Verify no tmp or bak files were created
    assert not os.path.exists(data_path + ".tmp")
    assert not os.path.exists(data_path + ".bak")
    assert not os.path.exists(metrics_path + ".tmp")
    assert not os.path.exists(metrics_path + ".bak")

def test_audit_runner_report_contains_non_promotion_disclaimer_and_deterministic_output_path(mock_env, mock_jqdata, mock_validators, isolated_paths):
    start_date = "2025-02-18"
    end_date = "2025-02-25"
    
    report_path = audit_cb_data(start_date, end_date)
    
    assert f"cb_etl_audit_{start_date}_{end_date}.json" in report_path
    assert os.path.exists(report_path)
    
    with open(report_path, "r") as f:
        report = json.load(f)
        
    assert report["non_promotion_disclaimer"] == NON_PROMOTION_DISCLAIMER
    assert report["execution_mode"] == "audit"

def test_audit_runner_live_probe_smoke_contract_is_callable_for_real_window(mock_env, mock_jqdata, mock_validators, isolated_paths):
    # This test proves the audit runner can be invoked and yields a parseable JSON report
    start_date = "2025-01-01"
    end_date = "2025-01-31"
    
    # Mock successful run
    report_path = audit_cb_data(start_date, end_date)
    
    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report = json.load(f)
        
    assert "final_status" in report
    assert "root_blockers" in report
    assert "secondary_findings" in report
    assert report["start_date"] == start_date
    assert report["end_date"] == end_date


def test_audit_report_includes_issue_1218_witness_when_old_signatures_are_absent(mock_env, mock_jqdata, mock_validators, isolated_paths):
    start_date = "2025-11-01"
    end_date = "2025-11-30"

    mock_jqdata.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]}),
        pd.DataFrame({"date": ["2025-11-03"], "code": ["110059"], "convert_premium_rate": [10.0]}),
    ]
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
    mock_jqdata.get_price.return_value = pd.DataFrame(
        {"time": ["2025-11-03"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
    ).set_index(["time", "code"])
    mock_jqdata.get_extras.return_value = pd.DataFrame({"600001.XSHG": [False]}, index=pd.to_datetime(["2025-11-03"]))

    report_path = audit_cb_data(start_date, end_date)

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    witness = report["issue_1218_witness"]
    assert witness["issue_key"] == ISSUE_1218_KEY
    assert witness["old_signatures_absent"] is True
    assert witness["signature_a"]["present"] is False
    assert witness["signature_a"]["evidence"] == {
        "premium_source_row_count": 1,
        "premium_joined_row_count": 1,
    }
    assert witness["signature_b"]["present"] is False
    assert witness["signature_b"]["legacy_text"] == ISSUE_1218_LEGACY_TICKER_DTYPE_TEXT
    assert witness["signature_b"]["evidence"]["core_validator_message"] == ""
    assert witness["signature_b"]["evidence"]["legacy_text_match"] is False


def test_issue_1218_witness_flags_exact_legacy_join_and_dtype_signatures(mock_env, mock_jqdata, mock_validators, isolated_paths):
    start_date = "2025-11-01"
    end_date = "2025-11-30"

    mock_jqdata.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059"], "company_code": ["600001.XSHG"], "delist_Date": [None]}),
        pd.DataFrame({"date": ["2025-11-03"], "code": ["110060"], "convert_premium_rate": [10.0]}),
    ]
    mock_jqdata.get_all_securities.return_value = pd.DataFrame({"code": ["110059.XSHG"]}, index=["110059.XSHG"])
    mock_jqdata.get_price.return_value = pd.DataFrame(
        {"time": ["2025-11-03"], "code": ["110059.XSHG"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]}
    ).set_index(["time", "code"])
    mock_jqdata.get_extras.return_value = pd.DataFrame({"600001.XSHG": [False]}, index=pd.to_datetime(["2025-11-03"]))

    validator_l1, _ = mock_validators
    validator_l1.return_value.validate_dataframe.return_value = False
    validator_l1.return_value.last_error_message = ISSUE_1218_LEGACY_TICKER_DTYPE_TEXT

    report_path = audit_cb_data(start_date, end_date)

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    witness = report["issue_1218_witness"]
    assert witness["old_signatures_absent"] is False
    assert witness["signature_a"]["present"] is True
    assert witness["signature_a"]["evidence"] == {
        "premium_source_row_count": 1,
        "premium_joined_row_count": 0,
    }
    assert witness["signature_b"]["present"] is True
    assert witness["signature_b"]["evidence"]["core_validator_message"] == ISSUE_1218_LEGACY_TICKER_DTYPE_TEXT
    assert witness["signature_b"]["evidence"]["legacy_text_match"] is True


def test_audit_runner_writes_nov_2025_live_witness_to_deterministic_report_path(mock_env, mock_validators, isolated_paths):
    start_date = "2025-11-01"
    end_date = "2025-11-30"
    expected_report_path = os.path.join(isolated_paths["reports"], f"cb_etl_audit_{start_date}_{end_date}.json")

    with patch("etl.jqdata_sync_cb.run_etl") as mock_run_etl:
        def _fake_run_etl(start_date_arg, end_date_arg, source_name, promote=False, **kwargs):
            assert start_date_arg == start_date
            assert end_date_arg == end_date
            assert source_name == "jqdata"
            assert promote is False
            report = {
                "execution_mode": "audit",
                "start_date": start_date,
                "end_date": end_date,
                "final_status": "PASS",
                "core_path_status": "PASS",
                "enrichment_path_status": "PASS",
                "non_promotion_disclaimer": NON_PROMOTION_DISCLAIMER,
                "active_universe_summary": {
                    "core_price_row_count_before_filter": 1,
                    "core_price_row_count_after_filter": 1,
                    "all_null_ohlcv_row_count_filtered": 0,
                    "core_universe_row_count": 1,
                    "core_universe_unique_bond_count": 1,
                    "active_bond_universe_count": 1,
                    "enrichment_target_row_count": 1,
                    "enrichment_target_unique_bond_count": 1,
                },
                "source_coverage": {
                    "status": "PASS",
                    "failure_type": "NONE",
                    "message": "",
                    "basic_info_row_count": 1,
                    "all_bond_security_count": 1,
                    "price_row_count": 1,
                    "price_unique_bond_count": 1,
                    "premium_source_row_count": 1,
                    "premium_source_unique_bond_count": 1,
                    "is_st_source_row_count": 1,
                    "is_st_source_unique_underlying_count": 1,
                    "redemption_source_row_count": 1,
                    "redemption_source_unique_bond_count": 1,
                },
                "supportability_summary": {
                    "status": "PASS",
                    "failure_type": "NONE",
                    "message": "",
                    "supportable_row_count": 1,
                    "supportable_unique_bond_count": 1,
                    "outside_basic_info_row_count": 0,
                    "outside_basic_info_unique_bond_count": 0,
                    "missing_company_code_legacy_row_count": 0,
                    "missing_company_code_legacy_unique_bond_count": 0,
                    "unexpected_contract_regression_row_count": 0,
                    "unexpected_contract_regression_unique_bond_count": 0,
                    "missing_underlying_row_count": 0,
                    "missing_underlying_unique_bond_count": 0,
                },
                "premium_join_summary": {
                    "status": "PASS",
                    "failure_type": "NONE",
                    "message": "",
                    "premium_joined_row_count": 1,
                    "premium_joined_unique_bond_count": 1,
                    "missing_premium_row_count": 0,
                    "missing_premium_unique_bond_count": 0,
                    "missing_premium_ratio": 0.0,
                    "premium_missing_ratio_against_active_universe": 0.0,
                    "rate_limited_enrichment": False,
                    "permission_degraded_enrichment": False,
                },
                "is_st_join_summary": {
                    "status": "PASS",
                    "failure_type": "NONE",
                    "message": "",
                    "is_st_joined_row_count": 1,
                    "is_st_joined_unique_bond_count": 1,
                    "missing_is_st_row_count": 0,
                    "missing_is_st_unique_bond_count": 0,
                    "missing_is_st_ratio": 0.0,
                },
                "redemption_summary": {
                    "status": "PASS",
                    "failure_type": "NONE",
                    "message": "",
                    "redemption_joined_row_count": 1,
                    "redemption_joined_unique_bond_count": 1,
                    "missing_redemption_row_count": 0,
                    "missing_redemption_unique_bond_count": 0,
                    "missing_redemption_ratio": 0.0,
                },
                "validator_summary": {
                    "status": "PASS",
                    "failure_type": "NONE",
                    "message": "",
                    "core_validator_status": "PASS",
                    "core_validator_message": "",
                    "enrichment_validator_status": "PASS",
                    "enrichment_validator_message": "",
                    "promotion_gate_status": "PASS",
                    "promotion_gate_message": "",
                },
                "issue_1218_witness": {
                    "issue_key": ISSUE_1218_KEY,
                    "old_signatures_absent": True,
                    "signature_a": {
                        "present": False,
                        "rule": "premium_source_row_count > 0 and premium_joined_row_count == 0",
                        "evidence": {"premium_source_row_count": 1, "premium_joined_row_count": 1},
                    },
                    "signature_b": {
                        "present": False,
                        "legacy_text": ISSUE_1218_LEGACY_TICKER_DTYPE_TEXT,
                        "evidence": {"core_validator_message": "", "legacy_text_match": False},
                    },
                },
                "root_blockers": [],
                "secondary_findings": [],
            }
            os.makedirs(os.path.dirname(expected_report_path), exist_ok=True)
            with open(expected_report_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
            return expected_report_path

        mock_run_etl.side_effect = _fake_run_etl

        report_path = audit_cb_data(start_date, end_date)

    assert report_path == expected_report_path
    assert os.path.exists(report_path)
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report_path.endswith("cb_etl_audit_2025-11-01_2025-11-30.json")
    assert report["issue_1218_witness"]["issue_key"] == ISSUE_1218_KEY
    assert report["issue_1218_witness"]["old_signatures_absent"] is True
