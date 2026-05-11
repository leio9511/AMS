import pytest
import pandas as pd
from datetime import datetime
from etl.redemption_derivation import derive_canonical_redemption_state

def create_base_ledger():
    return pd.DataFrame({
        'event_id': ['ev1'],
        'revision': [0],
        'is_active_revision': [True],
        'source_native_event_id': ['src_1'],
        'bond_code': ['110000.XSHG'],
        'announcement_date': ['2025-01-05'],
        'delisting_date': ['2025-01-10'],
        'source': ['dummy'],
        'updated_at': ['2025-01-01T00:00:00Z']
    })

def test_daily_derivation_window():
    ledger = create_base_ledger()
    # Test dates: before, exactly on announcement, inside window, on delisting, after
    target_dates = ['2025-01-04', '2025-01-05', '2025-01-07', '2025-01-10', '2025-01-11']
    
    df, traces = derive_canonical_redemption_state(ledger, target_dates)
    
    assert len(traces) == 0
    assert len(df) == 5
    
    # 2025-01-04 is before announcement -> False
    assert df.loc[df['date'] == '2025-01-04', 'redeem_risk'].iloc[0] == False
    # 2025-01-05 is exactly announcement -> True
    assert df.loc[df['date'] == '2025-01-05', 'redeem_risk'].iloc[0] == True
    # 2025-01-07 is inside -> True
    assert df.loc[df['date'] == '2025-01-07', 'redeem_risk'].iloc[0] == True
    # 2025-01-10 is exactly delisting -> False (exclusive)
    assert df.loc[df['date'] == '2025-01-10', 'redeem_risk'].iloc[0] == False
    # 2025-01-11 is after -> False
    assert df.loc[df['date'] == '2025-01-11', 'redeem_risk'].iloc[0] == False

def test_representative_event_selection():
    # Two distinct active events overlap
    ledger = pd.DataFrame({
        'event_id': ['ev1', 'ev2', 'ev3'],
        'revision': [0, 0, 0],
        'is_active_revision': [True, True, True],
        'source_native_event_id': ['src_1', 'src_2', 'src_3'],
        'bond_code': ['110000.XSHG', '110000.XSHG', '110000.XSHG'],
        'announcement_date': ['2025-01-02', '2025-01-02', '2025-01-01'], # ev3 is earliest announcement
        'delisting_date': ['2025-01-10', '2025-01-10', '2025-01-10'],
        'source': ['dummy', 'dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-01T11:00:00Z', '2024-12-31T00:00:00Z']
    })
    
    df, traces = derive_canonical_redemption_state(ledger, ['2025-01-05'])
    
    assert len(df) == 1
    # For representative selection rules:
    # 1. Earliest announcement_date -> ev3 (2025-01-01)
    # 2. Latest updated_at (if tied)
    # 3. Lexical min event_id (if still tied)
    row = df.iloc[0]
    assert row['redeem_risk'] == True
    assert row['representative_event_id'] == 'ev3'
    assert row['contributing_event_count'] == 3
    
    # Test tie-breaking for announcement_date
    ledger2 = pd.DataFrame({
        'event_id': ['ev1', 'ev2'],
        'revision': [0, 0],
        'is_active_revision': [True, True],
        'source_native_event_id': ['src_1', 'src_2'],
        'bond_code': ['110000.XSHG', '110000.XSHG'],
        'announcement_date': ['2025-01-02', '2025-01-02'], 
        'delisting_date': ['2025-01-10', '2025-01-10'],
        'source': ['dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-01T11:00:00Z'] # ev2 has latest updated_at
    })
    df2, traces2 = derive_canonical_redemption_state(ledger2, ['2025-01-05'])
    assert df2.iloc[0]['representative_event_id'] == 'ev2'

    # Test tie-breaking for both announcement_date and updated_at
    ledger3 = pd.DataFrame({
        'event_id': ['evB', 'evA'],
        'revision': [0, 0],
        'is_active_revision': [True, True],
        'source_native_event_id': ['src_B', 'src_A'],
        'bond_code': ['110000.XSHG', '110000.XSHG'],
        'announcement_date': ['2025-01-02', '2025-01-02'], 
        'delisting_date': ['2025-01-10', '2025-01-10'],
        'source': ['dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-01T10:00:00Z'] # Tie -> use lexical min event_id (evA)
    })
    df3, traces3 = derive_canonical_redemption_state(ledger3, ['2025-01-05'])
    assert df3.iloc[0]['representative_event_id'] == 'evA'

def test_coexistence_traceability():
    ledger = pd.DataFrame({
        'event_id': ['ev1', 'ev2'],
        'revision': [0, 0],
        'is_active_revision': [True, True],
        'source_native_event_id': ['src_1', 'src_2'],
        'bond_code': ['110000.XSHG', '110000.XSHG'],
        'announcement_date': ['2025-01-02', '2025-01-02'],
        'delisting_date': ['2025-01-10', '2025-01-10'],
        'source': ['dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-01T11:00:00Z'] # ev2 wins
    })
    
    df, traces = derive_canonical_redemption_state(ledger, ['2025-01-05'])
    
    assert len(df) == 1
    assert df.iloc[0]['redeem_risk'] == True
    
    assert len(traces) == 1
    trace = traces[0]
    assert trace['conflict_type'] == 'COEXIST_SAME_RISK_WINDOW'
    assert trace['date'] == '2025-01-05'
    assert trace['bond_code'] == '110000.XSHG'
    assert set(trace['contributing_event_ids']) == {'ev1', 'ev2'}
    assert trace['resolution_mode'] == 'representative_selected'
    assert trace['representative_event_id'] == 'ev2'
    assert trace['representative_revision'] == 0

def test_canonical_state_cardinality():
    ledger = pd.DataFrame({
        'event_id': ['ev1', 'ev2'],
        'revision': [0, 0],
        'is_active_revision': [True, True],
        'source_native_event_id': ['src_1', 'src_2'],
        'bond_code': ['110000.XSHG', '110001.XSHG'], # Different bonds
        'announcement_date': ['2025-01-02', '2025-01-05'],
        'delisting_date': ['2025-01-10', '2025-01-15'],
        'source': ['dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-01T11:00:00Z']
    })
    
    target_dates = ['2025-01-01', '2025-01-06']
    df, traces = derive_canonical_redemption_state(ledger, target_dates)
    
    # 2 dates, 2 bonds -> exactly 4 rows
    assert len(df) == 4
    
    # Each date + bond pair appears exactly once
    counts = df.groupby(['date', 'bond_code']).size()
    assert (counts == 1).all()

def test_active_revision_enforcement():
    ledger = pd.DataFrame({
        'event_id': ['ev1', 'ev1'],
        'revision': [0, 1],
        'is_active_revision': [False, True], # Revision 0 is inactive, 1 is active
        'source_native_event_id': ['src_1', 'src_1'],
        'bond_code': ['110000.XSHG', '110000.XSHG'],
        'announcement_date': ['2025-01-02', '2025-01-05'], # Inactive announced earlier
        'delisting_date': ['2025-01-10', '2025-01-15'],
        'source': ['dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-04T10:00:00Z']
    })
    
    # Test date where inactive revision 0 would have triggered True, but active 1 triggers False
    df, traces = derive_canonical_redemption_state(ledger, ['2025-01-03'])
    
    assert len(df) == 1
    assert df.iloc[0]['redeem_risk'] == False # Since revision 0 is ignored and revision 1 hasn't started
    assert pd.isna(df.iloc[0]['representative_event_id'])

    # Test date where active revision 1 triggers True
    df2, traces2 = derive_canonical_redemption_state(ledger, ['2025-01-06'])
    assert df2.iloc[0]['redeem_risk'] == True
    assert df2.iloc[0]['representative_event_id'] == 'ev1'
    assert df2.iloc[0]['representative_revision'] == 1

def test_conflict_multiple_active_revisions():
    ledger = pd.DataFrame({
        'event_id': ['ev1', 'ev1'],
        'revision': [0, 1],
        'is_active_revision': [True, True], # Both active! Error in ledger.
        'source_native_event_id': ['src_1', 'src_1'],
        'bond_code': ['110000.XSHG', '110000.XSHG'],
        'announcement_date': ['2025-01-02', '2025-01-05'], 
        'delisting_date': ['2025-01-10', '2025-01-15'],
        'source': ['dummy', 'dummy'],
        'updated_at': ['2025-01-01T10:00:00Z', '2025-01-04T10:00:00Z']
    })
    
    df, traces = derive_canonical_redemption_state(ledger, ['2025-01-06'])
    
    assert len(df) == 1
    assert pd.isna(df.iloc[0]['redeem_risk']) # Should be pd.NA
    
    assert len(traces) == 1
    trace = traces[0]
    assert trace['conflict_type'] == 'CONFLICT_MULTIPLE_ACTIVE_REVISIONS_FOR_EVENT'
    assert trace['resolution_mode'] == 'blocked'
    assert trace['representative_event_id'] is None
