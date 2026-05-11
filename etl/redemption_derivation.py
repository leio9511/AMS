import pandas as pd
from typing import List, Dict, Any, Tuple

def derive_canonical_redemption_state(
    ledger_df: pd.DataFrame, 
    target_dates: List[str]
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Derives canonical daily state and conflict/coexistence traces from a persisted ledger.
    """
    traces = []
    canonical_rows = []

    # Ensure canonical structure even for empty ledger
    if ledger_df.empty:
        df = pd.DataFrame(columns=[
            'date', 'bond_code', 'redeem_risk', 'representative_event_id',
            'representative_revision', 'contributing_event_count'
        ])
        df['redeem_risk'] = df['redeem_risk'].astype('boolean')
        df['representative_revision'] = df['representative_revision'].astype('Int64')
        df['contributing_event_count'] = df['contributing_event_count'].astype('Int64')
        return df, traces

    # Filter active revisions
    if 'is_active_revision' not in ledger_df.columns:
        raise ValueError("ledger_df must contain 'is_active_revision' column")

    active_ledger = ledger_df[ledger_df['is_active_revision'] == True].copy()
    
    if active_ledger.empty:
        # If no active events, bonds might still need to be reported as False if we know them.
        # Let's derive the bonds from the whole ledger instead.
        all_bonds = ledger_df['bond_code'].unique() if 'bond_code' in ledger_df.columns else []
    else:
        # It's safer to base known bonds on the entire ledger so inactive bonds also get False rows
        all_bonds = ledger_df['bond_code'].unique()

        active_ledger['announcement_date'] = pd.to_datetime(active_ledger['announcement_date']).dt.normalize()
        active_ledger['delisting_date'] = pd.to_datetime(active_ledger['delisting_date']).dt.normalize()
        active_ledger['updated_at'] = pd.to_datetime(active_ledger['updated_at'])

    for d_str in target_dates:
        d_date = pd.to_datetime(d_str).normalize()
        
        for bond in all_bonds:
            if active_ledger.empty:
                canonical_rows.append({
                    'date': d_str,
                    'bond_code': bond,
                    'redeem_risk': False,
                    'representative_event_id': None,
                    'representative_revision': None,
                    'contributing_event_count': 0
                })
                continue

            bond_events = active_ledger[active_ledger['bond_code'] == bond]
            
            # Find events that overlap this date
            overlapping_events = bond_events[
                (bond_events['announcement_date'] <= d_date) &
                (d_date < bond_events['delisting_date'])
            ]
            
            if overlapping_events.empty:
                canonical_rows.append({
                    'date': d_str,
                    'bond_code': bond,
                    'redeem_risk': False,
                    'representative_event_id': None,
                    'representative_revision': None,
                    'contributing_event_count': 0
                })
                continue

            # Check for CONFLICT_MULTIPLE_ACTIVE_REVISIONS_FOR_EVENT
            event_id_counts = overlapping_events.groupby('event_id').size()
            multiple_revisions = event_id_counts[event_id_counts > 1].index.tolist()
            
            if multiple_revisions:
                # We have a conflict!
                # We record a trace and emit a blocked row.
                contributing_ids = overlapping_events['event_id'].tolist()
                traces.append({
                    "date": d_str,
                    "bond_code": bond,
                    "conflict_type": "CONFLICT_MULTIPLE_ACTIVE_REVISIONS_FOR_EVENT",
                    "contributing_event_ids": list(set(contributing_ids)),
                    "resolution_mode": "blocked",
                    "representative_event_id": None,
                    "representative_revision": None
                })
                canonical_rows.append({
                    'date': d_str,
                    'bond_code': bond,
                    'redeem_risk': pd.NA,
                    'representative_event_id': None,
                    'representative_revision': None,
                    'contributing_event_count': len(overlapping_events)
                })
                continue
                
            # Coexistence and Representative Selection
            # Sort to find representative
            sorted_events = overlapping_events.sort_values(
                by=['announcement_date', 'updated_at', 'event_id'],
                ascending=[True, False, True]
            )
            
            rep_event = sorted_events.iloc[0]
            contributing_ids = sorted_events['event_id'].tolist()
            
            if len(contributing_ids) > 1:
                traces.append({
                    "date": d_str,
                    "bond_code": bond,
                    "conflict_type": "COEXIST_SAME_RISK_WINDOW",
                    "contributing_event_ids": contributing_ids,
                    "resolution_mode": "representative_selected",
                    "representative_event_id": rep_event['event_id'],
                    "representative_revision": rep_event['revision']
                })

            canonical_rows.append({
                'date': d_str,
                'bond_code': bond,
                'redeem_risk': True,
                'representative_event_id': rep_event['event_id'],
                'representative_revision': rep_event['revision'],
                'contributing_event_count': len(contributing_ids)
            })

    df = pd.DataFrame(canonical_rows)
    if not df.empty:
        df['redeem_risk'] = df['redeem_risk'].astype('boolean')
        df['representative_revision'] = df['representative_revision'].astype('Int64')
        df['contributing_event_count'] = df['contributing_event_count'].astype('Int64')
    else:
        df = pd.DataFrame(columns=[
            'date', 'bond_code', 'redeem_risk', 'representative_event_id',
            'representative_revision', 'contributing_event_count'
        ])
        df['redeem_risk'] = df['redeem_risk'].astype('boolean')
        df['representative_revision'] = df['representative_revision'].astype('Int64')
        df['contributing_event_count'] = df['contributing_event_count'].astype('Int64')

    return df, traces
