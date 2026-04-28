import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from etl.jqdata_sync_cb import (
    StagedPipeline,
    SourceAcquisitionStage,
    SupportabilityStage,
    SUPPORTABILITY_REGRESSION_ERROR,
    sync_cb_data
)

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("JQDATA_USER", "fake_user")
    monkeypatch.setenv("JQDATA_PWD", "fake_pwd")

@pytest.fixture
def mock_jqdata():
    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock:
        yield mock

def test_pipeline_stage_a_success(mock_jqdata):
    # Mock Stage A responses
    mock_jqdata.bond.run_query.return_value = pd.DataFrame({"code": ["123456.SH"], "company_code": ["600000"]})
    mock_jqdata.get_all_securities.return_value = pd.DataFrame(index=["123456.SH"])
    
    index = pd.MultiIndex.from_tuples(
        [(pd.to_datetime("2025-01-06"), "123456.SH")],
        names=["time", "code"]
    )
    mock_jqdata.get_price.return_value = pd.DataFrame({
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]
    }, index=index)

    pipeline = StagedPipeline([
        SourceAcquisitionStage(start_date="2025-01-06", end_date="2025-01-07")
    ])
    results = pipeline.run()

    assert results["source_coverage"]["status"] == "PASS"
    assert results["source_coverage"]["basic_info_row_count"] > 0
    assert results["source_coverage"]["price_row_count"] > 0

def test_pipeline_stage_a_failure_propagation(mock_jqdata, monkeypatch):
    # Mock Stage A failure (e.g., Auth failure)
    mock_jqdata.auth.side_effect = Exception("Auth failed")

    pipeline = StagedPipeline([
        SourceAcquisitionStage(start_date="2025-01-06", end_date="2025-01-07"),
        SupportabilityStage(start_date="2025-01-06")
    ])
    results = pipeline.run(stop_on_failure=False)

    assert results["source_coverage"]["status"] == "FAIL"
    assert results["source_coverage"]["failure_type"] == "SOURCE_AUTH_FAILURE"
    assert results["supportability_summary"]["status"] == "NOT_RUN"
    assert results["supportability_summary"]["message"] == "Skipped because Stage A failed."

def test_pipeline_stage_b_supportability_regression(mock_jqdata):
    # Mock Stage A success
    mock_jqdata.bond.run_query.return_value = pd.DataFrame({"code": ["123456.SH"]}) # Missing company_code
    mock_jqdata.get_all_securities.return_value = pd.DataFrame(index=["123456.SH"])
    
    index = pd.MultiIndex.from_tuples(
        [(pd.to_datetime("2025-01-06"), "123456.SH")],
        names=["time", "code"]
    )
    mock_jqdata.get_price.return_value = pd.DataFrame({
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]
    }, index=index)

    pipeline = StagedPipeline([
        SourceAcquisitionStage(start_date="2025-01-06", end_date="2025-01-07"),
        SupportabilityStage(start_date="2025-01-06")
    ])
    results = pipeline.run(stop_on_failure=False)

    assert results["supportability_summary"]["status"] == "FAIL"
    assert results["supportability_summary"]["failure_type"] == "SUPPORTABILITY_REGRESSION"
    assert results["supportability_summary"]["unexpected_contract_regression_row_count"] > 0

def test_promote_runner_behavior_unchanged(mock_jqdata):
    # Mock Stage A success but Stage B failure (regression)
    mock_jqdata.bond.run_query.return_value = pd.DataFrame({"code": ["123456.SH"]}) # Missing company_code
    mock_jqdata.get_all_securities.return_value = pd.DataFrame(index=["123456.SH"])
    
    index = pd.MultiIndex.from_tuples(
        [(pd.to_datetime("2025-01-06"), "123456.SH")],
        names=["time", "code"]
    )
    mock_jqdata.get_price.return_value = pd.DataFrame({
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]
    }, index=index)

    with pytest.raises(ValueError, match=SUPPORTABILITY_REGRESSION_ERROR):
        sync_cb_data(start_date="2025-01-06", end_date="2025-01-07")

def test_audit_runner_full_schema_and_file_output(mock_jqdata, tmp_path):
    from etl.jqdata_sync_cb import CBETLAuditRunner
    import os
    import json
    
    # Mock Stage A responses
    mock_jqdata.bond.run_query.return_value = pd.DataFrame({"code": ["123456.SH"], "company_code": ["600000"]})
    mock_jqdata.get_all_securities.return_value = pd.DataFrame(index=["123456.SH"])
    
    index = pd.MultiIndex.from_tuples(
        [(pd.to_datetime("2025-01-06"), "123456.SH")],
        names=["time", "code"]
    )
    mock_jqdata.get_price.return_value = pd.DataFrame({
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]
    }, index=index)

    with patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True) as mock_open:
        
        runner = CBETLAuditRunner(start_date="2025-01-06", end_date="2025-01-07")
        report = runner.run()

        # Check Stage B metrics
        assert "missing_underlying_row_count" in report["supportability_summary"]
        assert report["supportability_summary"]["missing_underlying_row_count"] == 0

        # Check full schema for Stage C (Premium)
        premium = report["premium_join_summary"]
        for field in ["status", "failure_type", "premium_joined_row_count", "missing_premium_row_count", "missing_premium_ratio"]:
            assert field in premium
        
        # Check NOT_RUN propagation message
        assert premium["status"] == "NOT_RUN"
        assert "Stage not implemented" in premium["message"]

        # Verify file output was attempted
        assert mock_open.called
        args, _ = mock_open.call_args
        assert "cb_etl_audit_2025-01-06_2025-01-07.json" in args[0]

def test_audit_runner_stage_a_failure_propagation(mock_jqdata):
    from etl.jqdata_sync_cb import CBETLAuditRunner
    # Mock Stage A failure
    mock_jqdata.auth.side_effect = Exception("Auth failed")

    runner = CBETLAuditRunner(start_date="2025-01-06", end_date="2025-01-07")
    
    with patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    assert report["source_coverage"]["status"] == "FAIL"
    assert report["supportability_summary"]["status"] == "NOT_RUN"
    assert report["supportability_summary"]["message"] == "Skipped because Stage A failed."
    assert report["premium_join_summary"]["status"] == "NOT_RUN"
    assert report["premium_join_summary"]["message"] == "Skipped because Stage A failed."

def test_audit_runner_secondary_findings_missing_underlying(mock_jqdata):
    from etl.jqdata_sync_cb import CBETLAuditRunner
    # Mock Stage A success but with missing company_code for some rows
    df_bonds_info = pd.DataFrame({"code": ["123456.SH"], "company_code": [None]})
    mock_jqdata.bond.run_query.return_value = df_bonds_info
    mock_jqdata.get_all_securities.return_value = pd.DataFrame(index=["123456.SH"])
    
    index = pd.MultiIndex.from_tuples(
        [(pd.to_datetime("2025-01-06"), "123456.SH")],
        names=["time", "code"]
    )
    mock_jqdata.get_price.return_value = pd.DataFrame({
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]
    }, index=index)

    runner = CBETLAuditRunner(start_date="2025-01-06", end_date="2025-01-07")
    
    with patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    assert report["supportability_summary"]["missing_underlying_row_count"] > 0
    
    # Check secondary findings
    found = False
    for finding in report["secondary_findings"]:
        if finding["type"] == "MISSING_UNDERLYING_TICKER_ROWS":
            found = True
            break
    assert found, "MISSING_UNDERLYING_TICKER_ROWS should be in secondary_findings"

