import os
import json
import pandas as pd
import pytest
from datetime import datetime
from etl.redemption_pipeline import run_redemption_wave3_pipeline

def test_end_to_end_pipeline_execution(tmp_path):
    import_csv = tmp_path / "import.csv"
    ledger_csv = tmp_path / "ledger.csv"
    canonical_csv = tmp_path / "canonical.csv"
    trace_json = tmp_path / "trace.json"
    
    # Create dummy import facts
    df_import = pd.DataFrame([
        {
            "source_native_event_id": "N1",
            "bond_code": "113001",
            "announcement_date": "2025-01-01",
            "delisting_date": "2025-01-10",
            "source": "SRC1",
            "updated_at": "2025-01-01T00:00:00Z"
        },
        {
            "source_native_event_id": "", # Invalid, missing id
            "bond_code": "113002",
            "announcement_date": "2025-01-01",
            "delisting_date": "2025-01-10",
            "source": "SRC1",
            "updated_at": "2025-01-01T00:00:00Z"
        }
    ])
    df_import.to_csv(import_csv, index=False)
    
    target_dates = ["2025-01-05"]
    
    run_redemption_wave3_pipeline(
        str(import_csv),
        str(ledger_csv),
        str(canonical_csv),
        str(trace_json),
        target_dates
    )
    
    assert ledger_csv.exists()
    assert canonical_csv.exists()
    assert trace_json.exists()
    
    df_ledger = pd.read_csv(ledger_csv)
    assert len(df_ledger) == 1
    assert df_ledger.iloc[0]["event_id"] == "SRC1:N1"
    
    df_canon = pd.read_csv(canonical_csv)
    assert len(df_canon) == 1
    assert df_canon.iloc[0]["bond_code"] == 113001 or str(df_canon.iloc[0]["bond_code"]) == "113001"
    assert df_canon.iloc[0]["redeem_risk"] == True
    
def test_trace_artifact_schema_compliance(tmp_path):
    import_csv = tmp_path / "import.csv"
    ledger_csv = tmp_path / "ledger.csv"
    canonical_csv = tmp_path / "canonical.csv"
    trace_json = tmp_path / "trace.json"
    
    df_import = pd.DataFrame([
        {
            "source_native_event_id": "N1",
            "bond_code": "113001",
            "announcement_date": "2025-01-01",
            "delisting_date": "2025-01-10",
            "source": "SRC1",
            "updated_at": "2025-01-01T00:00:00Z"
        }
    ])
    df_import.to_csv(import_csv, index=False)
    
    run_redemption_wave3_pipeline(
        str(import_csv),
        str(ledger_csv),
        str(canonical_csv),
        str(trace_json),
        ["2025-01-05"]
    )
    
    with open(trace_json, "r", encoding="utf-8") as f:
        trace_data = json.load(f)
        
    expected_keys = [
        "ingress_artifact_path",
        "ledger_artifact_path",
        "trace_generated_at",
        "accepted_fact_count",
        "rejected_fact_count",
        "updated_revision_count",
        "rejected_facts",
        "conflict_rows",
        "daily_state_trace_examples"
    ]
    for key in expected_keys:
        assert key in trace_data
        
    assert trace_data["accepted_fact_count"] == 1
    assert trace_data["rejected_fact_count"] == 0
    
    examples = trace_data["daily_state_trace_examples"]
    assert len(examples) == 1
    example = examples[0]
    assert example["date"] == "2025-01-05"
    assert example["bond_code"] == "113001"
    assert example["redeem_risk"] is True
    assert example["representative_event_id"] == "SRC1:N1"
    assert example["announcement_date"] == "2025-01-01"
    assert example["delisting_date"] == "2025-01-10"

def test_provider_snapshot_independence(tmp_path):
    import_csv = tmp_path / "import.csv"
    ledger_csv = tmp_path / "ledger.csv"
    canonical_csv = tmp_path / "canonical.csv"
    trace_json = tmp_path / "trace.json"
    
    # Run 1: with event
    df_import = pd.DataFrame([
        {
            "source_native_event_id": "N1",
            "bond_code": "113001",
            "announcement_date": "2025-01-01",
            "delisting_date": "2025-01-10",
            "source": "SRC1",
            "updated_at": "2025-01-01T00:00:00Z"
        }
    ])
    df_import.to_csv(import_csv, index=False)
    
    run_redemption_wave3_pipeline(
        str(import_csv),
        str(ledger_csv),
        str(canonical_csv),
        str(trace_json),
        ["2025-01-02"]
    )
    
    # Run 2: NO new events (simulating provider didn't send anything today), but requesting future dates
    df_import_empty = pd.DataFrame(columns=[
        "source_native_event_id", "bond_code", "announcement_date", 
        "delisting_date", "source", "updated_at"
    ])
    df_import_empty.to_csv(import_csv, index=False)
    
    run_redemption_wave3_pipeline(
        str(import_csv),
        str(ledger_csv),
        str(canonical_csv),
        str(trace_json),
        ["2025-01-03", "2025-01-04", "2025-01-11"]
    )
    
    df_canon = pd.read_csv(canonical_csv)
    # 3 target dates
    assert len(df_canon) == 3
    
    # Let's check results based on existing ledger
    df_03 = df_canon[df_canon["date"] == "2025-01-03"].iloc[0]
    assert df_03["redeem_risk"] == True
    
    df_04 = df_canon[df_canon["date"] == "2025-01-04"].iloc[0]
    assert df_04["redeem_risk"] == True
    
    df_11 = df_canon[df_canon["date"] == "2025-01-11"].iloc[0]
    assert df_11["redeem_risk"] == False
