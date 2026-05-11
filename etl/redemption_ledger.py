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
    df = pd.read_csv(path, dtype=str)
    return df

def read_ledger(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    df = pd.read_csv(path, dtype=str)
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

    if source == "nan": source = ""
    if native_id == "nan": native_id = ""
    if ann_date == "nan": ann_date = ""
    if del_date == "nan": del_date = ""

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

        event_mask = new_ledger["event_id"] == event_id
        event_ledger = new_ledger[event_mask]
        
        if event_ledger.empty:
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
            new_ledger = pd.concat([new_ledger, pd.DataFrame([new_row])], ignore_index=True)
        else:
            active_mask = event_mask & (new_ledger["is_active_revision"] == True)
            active_revision_df = new_ledger[active_mask]
            if not active_revision_df.empty:
                active_revision = active_revision_df.iloc[0]
                
                # Compare business fields exactly
                bus_fields = ["bond_code", "announcement_date", "delisting_date"]
                is_duplicate = True
                for field in bus_fields:
                    if str(active_revision[field]) != str(row[field]):
                        is_duplicate = False
                        break
                
                if not is_duplicate:
                    # Update / Correction
                    new_ledger.loc[active_mask, "is_active_revision"] = False
                    prev_max_revision = event_ledger["revision"].max()
                    
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
                    new_ledger = pd.concat([new_ledger, pd.DataFrame([new_row])], ignore_index=True)
            else:
                prev_max_revision = event_ledger["revision"].max()
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
                new_ledger = pd.concat([new_ledger, pd.DataFrame([new_row])], ignore_index=True)

    if not new_ledger.empty:
        new_ledger["revision"] = new_ledger["revision"].astype(int)
        new_ledger["is_active_revision"] = new_ledger["is_active_revision"].astype(bool)

    return new_ledger, rejected_facts
