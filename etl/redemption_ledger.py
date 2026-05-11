import os
import pandas as pd
from typing import Tuple, List, Dict, Any

IMPORT_COLUMNS = [
    "source_native_event_id", 
    "bond_code", 
    "announcement_date", 
    "delisting_date", 
    "source", 
    "updated_at"
]

LEDGER_COLUMNS = [
    "event_id", 
    "revision", 
    "is_active_revision",
    "source_native_event_id", 
    "bond_code", 
    "announcement_date", 
    "delisting_date", 
    "source", 
    "updated_at"
]

def read_import_facts(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=IMPORT_COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df

def read_ledger(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "revision" in df.columns:
        df["revision"] = df["revision"].astype(int)
    if "is_active_revision" in df.columns:
        df["is_active_revision"] = df["is_active_revision"].astype(str).str.lower() == 'true'
    return df

def write_ledger(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)

def _validate_and_generate_identity(row: pd.Series) -> Tuple[bool, str, str]:
    # Returns (is_valid, reason, event_id)
    source = str(row.get("source", "")).strip()
    native_id = str(row.get("source_native_event_id", "")).strip()
    ann_date = str(row.get("announcement_date", "")).strip()
    del_date = str(row.get("delisting_date", "")).strip()

    if not native_id:
        return False, "MISSING_SOURCE_NATIVE_EVENT_ID", ""
    if not ann_date:
        return False, "MISSING_ANNOUNCEMENT_DATE", ""
    if not del_date:
        return False, "MISSING_DELISTING_DATE", ""
    if ann_date > del_date:
        return False, "INVALID_DATE_ORDER", ""

    event_id = f"{source}:{native_id}"
    return True, "", event_id

def process_ingress_to_ledger(ingress_df: pd.DataFrame, ledger_df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    rejected_facts = []
    
    if ledger_df.empty:
        new_ledger = pd.DataFrame(columns=LEDGER_COLUMNS)
    else:
        new_ledger = ledger_df.copy()
        
    # To handle 'nan' string values gracefully if ingress_df wasn't loaded with keep_default_na=False
    # We apply fillna on a copy, avoiding modifying the input dataframe directly
    ingress_df = ingress_df.fillna('')

    new_rows = []
    
    max_revisions = {}
    active_states = {}
    active_in_new_rows = {}
    
    if not new_ledger.empty:
        # Prepopulate max_revisions
        max_revs = new_ledger.groupby("event_id")["revision"].max()
        for ev_id, rev in max_revs.items():
            max_revisions[ev_id] = rev
            
        # Prepopulate active_states
        active_mask = new_ledger["is_active_revision"] == True
        active_df = new_ledger[active_mask]
        for _, r in active_df.iterrows():
            active_states[r["event_id"]] = {
                "bond_code": str(r["bond_code"]),
                "announcement_date": str(r["announcement_date"]),
                "delisting_date": str(r["delisting_date"])
            }

    for _, row in ingress_df.iterrows():
        is_valid, reason, event_id = _validate_and_generate_identity(row)
        if not is_valid:
            rejected_facts.append({
                "source_native_event_id": str(row.get("source_native_event_id", "")),
                "bond_code": str(row.get("bond_code", "")),
                "reason": reason,
                "source": str(row.get("source", ""))
            })
            continue

        bus_fields = ["bond_code", "announcement_date", "delisting_date"]
        current_state = {f: str(row[f]) for f in bus_fields}

        if event_id not in max_revisions:
            # New Event
            new_row = {
                "event_id": event_id,
                "revision": 0,
                "is_active_revision": True,
                "source_native_event_id": row["source_native_event_id"],
                "bond_code": row["bond_code"],
                "announcement_date": row["announcement_date"],
                "delisting_date": row["delisting_date"],
                "source": row["source"],
                "updated_at": row["updated_at"]
            }
            new_rows.append(new_row)
            max_revisions[event_id] = 0
            active_states[event_id] = current_state
            active_in_new_rows[event_id] = len(new_rows) - 1
            
        else:
            active_state = active_states.get(event_id)
            if active_state:
                is_duplicate = all(active_state[f] == current_state[f] for f in bus_fields)
                if not is_duplicate:
                    # Update / Correction
                    if event_id in active_in_new_rows:
                        idx = active_in_new_rows[event_id]
                        new_rows[idx]["is_active_revision"] = False
                    else:
                        mask = (new_ledger["event_id"] == event_id) & (new_ledger["is_active_revision"] == True)
                        new_ledger.loc[mask, "is_active_revision"] = False
                        
                    prev_max_revision = max_revisions[event_id]
                    new_row = {
                        "event_id": event_id,
                        "revision": prev_max_revision + 1,
                        "is_active_revision": True,
                        "source_native_event_id": row["source_native_event_id"],
                        "bond_code": row["bond_code"],
                        "announcement_date": row["announcement_date"],
                        "delisting_date": row["delisting_date"],
                        "source": row["source"],
                        "updated_at": row["updated_at"]
                    }
                    new_rows.append(new_row)
                    max_revisions[event_id] = prev_max_revision + 1
                    active_states[event_id] = current_state
                    active_in_new_rows[event_id] = len(new_rows) - 1
            else:
                prev_max_revision = max_revisions[event_id]
                new_row = {
                    "event_id": event_id,
                    "revision": prev_max_revision + 1,
                    "is_active_revision": True,
                    "source_native_event_id": row["source_native_event_id"],
                    "bond_code": row["bond_code"],
                    "announcement_date": row["announcement_date"],
                    "delisting_date": row["delisting_date"],
                    "source": row["source"],
                    "updated_at": row["updated_at"]
                }
                new_rows.append(new_row)
                max_revisions[event_id] = prev_max_revision + 1
                active_states[event_id] = current_state
                active_in_new_rows[event_id] = len(new_rows) - 1

    if new_rows:
        new_ledger = pd.concat([new_ledger, pd.DataFrame(new_rows)], ignore_index=True)

    if not new_ledger.empty:
        new_ledger["revision"] = new_ledger["revision"].astype(int)
        new_ledger["is_active_revision"] = new_ledger["is_active_revision"].astype(bool)

    return new_ledger, rejected_facts
