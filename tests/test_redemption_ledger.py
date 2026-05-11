import pandas as pd
import pytest
from etl.redemption_ledger import process_ingress_to_ledger, LEDGER_COLUMNS

def test_event_identity_authority():
    # Concatenates source and source_native_event_id correctly.
    # Empty/null native IDs are rejected and added to the rejected facts list.
    ingress_data = [
        {"source_native_event_id": "123", "bond_code": "110001", "announcement_date": "2023-01-01", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01T00:00:00Z"},
        {"source_native_event_id": "", "bond_code": "110002", "announcement_date": "2023-01-01", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01T00:00:00Z"},
    ]
    ingress_df = pd.DataFrame(ingress_data)
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger, rejected = process_ingress_to_ledger(ingress_df, ledger_df)
    
    assert len(new_ledger) == 1
    assert new_ledger.iloc[0]["event_id"] == "srcA:123"
    
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "MISSING_SOURCE_NATIVE_EVENT_ID"
    assert rejected[0]["source_native_event_id"] == ""


def test_revision_classification_new_event():
    # A previously unseen event gets revision=0 and is_active_revision=True.
    ingress_data = [
        {"source_native_event_id": "123", "bond_code": "110001", "announcement_date": "2023-01-01", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01T00:00:00Z"}
    ]
    ingress_df = pd.DataFrame(ingress_data)
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger, rejected = process_ingress_to_ledger(ingress_df, ledger_df)
    
    assert len(new_ledger) == 1
    assert len(rejected) == 0
    row = new_ledger.iloc[0]
    assert row["revision"] == 0
    assert row["is_active_revision"] == True
    assert row["event_id"] == "srcA:123"

def test_revision_classification_duplicate():
    # Re-importing the exact same facts produces no new rows in the ledger; previous active revision remains untouched.
    ingress_data = [
        {"source_native_event_id": "123", "bond_code": "110001", "announcement_date": "2023-01-01", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01T00:00:00Z"}
    ]
    ingress_df = pd.DataFrame(ingress_data)
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    # First import
    new_ledger, _ = process_ingress_to_ledger(ingress_df, ledger_df)
    
    # Second import (same facts)
    new_ledger2, _ = process_ingress_to_ledger(ingress_df, new_ledger)
    
    assert len(new_ledger2) == 1
    assert new_ledger2.iloc[0]["revision"] == 0
    assert new_ledger2.iloc[0]["is_active_revision"] == True


def test_revision_classification_update():
    # Importing changed facts for an existing event_id increments revision, sets is_active_revision=True for the new row, and sets False for the old row.
    ingress_data_1 = [
        {"source_native_event_id": "123", "bond_code": "110001", "announcement_date": "2023-01-01", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01T00:00:00Z"}
    ]
    ingress_df_1 = pd.DataFrame(ingress_data_1)
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger_1, _ = process_ingress_to_ledger(ingress_df_1, ledger_df)
    
    # Update facts (changed delisting date)
    ingress_data_2 = [
        {"source_native_event_id": "123", "bond_code": "110001", "announcement_date": "2023-01-01", "delisting_date": "2023-01-15", "source": "srcA", "updated_at": "2023-01-02T00:00:00Z"}
    ]
    ingress_df_2 = pd.DataFrame(ingress_data_2)
    
    new_ledger_2, _ = process_ingress_to_ledger(ingress_df_2, new_ledger_1)
    
    assert len(new_ledger_2) == 2
    
    rev0 = new_ledger_2[new_ledger_2["revision"] == 0].iloc[0]
    rev1 = new_ledger_2[new_ledger_2["revision"] == 1].iloc[0]
    
    assert rev0["is_active_revision"] == False
    assert rev1["is_active_revision"] == True
    assert rev1["delisting_date"] == "2023-01-15"


def test_date_validation_rejection():
    # Rows with missing dates or announcement_date > delisting_date are rejected and returned in the rejected list.
    ingress_data = [
        # Valid
        {"source_native_event_id": "1", "bond_code": "110001", "announcement_date": "2023-01-01", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01"},
        # Missing ann date
        {"source_native_event_id": "2", "bond_code": "110002", "announcement_date": "", "delisting_date": "2023-01-10", "source": "srcA", "updated_at": "2023-01-01"},
        # Missing del date
        {"source_native_event_id": "3", "bond_code": "110003", "announcement_date": "2023-01-01", "delisting_date": "", "source": "srcA", "updated_at": "2023-01-01"},
        # Invalid date order
        {"source_native_event_id": "4", "bond_code": "110004", "announcement_date": "2023-01-10", "delisting_date": "2023-01-01", "source": "srcA", "updated_at": "2023-01-01"}
    ]
    ingress_df = pd.DataFrame(ingress_data)
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger, rejected = process_ingress_to_ledger(ingress_df, ledger_df)
    
    assert len(new_ledger) == 1
    assert new_ledger.iloc[0]["event_id"] == "srcA:1"
    
    assert len(rejected) == 3
    reasons = set(r["reason"] for r in rejected)
    assert reasons == {"MISSING_ANNOUNCEMENT_DATE", "MISSING_DELISTING_DATE", "INVALID_DATE_ORDER"}
