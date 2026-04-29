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

@pytest.fixture
def isolated_paths(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    
    mock_data_path = str(data_dir / "cb_history_factors.csv")
    mock_metrics_path = str(data_dir / "cb_history_factors.metrics.json")
    mock_reports_dir = str(reports_dir)
    
    import os
    original_os_path_join = os.path.join
    
    def mock_join(d, f):
        if "reports" in d:
            return original_os_path_join(mock_reports_dir, f)
        return original_os_path_join(d, f)

    with patch("etl.jqdata_sync_cb.DATA_PATH", mock_data_path), \
         patch("etl.jqdata_sync_cb.METRICS_PATH", mock_metrics_path), \
         patch("os.makedirs"), \
         patch("os.path.join", side_effect=mock_join):
             yield {
                 "data": mock_data_path,
                 "metrics": mock_metrics_path,
                 "reports": mock_reports_dir
             }

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
