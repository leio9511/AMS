import json
import os
from datetime import datetime, timezone
import pandas as pd
from typing import List

from etl.redemption_ledger import (
    read_import_facts,
    read_ledger,
    write_ledger,
    process_ingress_to_ledger
)
from etl.redemption_derivation import derive_canonical_redemption_state

def run_redemption_wave3_pipeline(
    import_csv_path: str,
    ledger_csv_path: str,
    canonical_csv_path: str,
    trace_json_path: str,
    target_dates: List[str]
):
    """
    Executes the Wave 3 redemption pipeline:
    1. Update persisted ledger from import facts.
    2. Derive canonical state for target dates.
    3. Generate trace artifact.
    """
    # 1. Update Ledger
    ingress_df = read_import_facts(import_csv_path)
    old_ledger_df = read_ledger(ledger_csv_path)
    
    new_ledger_df, rejected_facts = process_ingress_to_ledger(ingress_df, old_ledger_df)
    
    write_ledger(new_ledger_df, ledger_csv_path)
    
    # Calculate stats
    total_ingress = len(ingress_df)
    rejected_count = len(rejected_facts)
    accepted_count = total_ingress - rejected_count
    
    if "revision" in new_ledger_df.columns:
        updated_revision_count = int((new_ledger_df["revision"] > 0).sum())
    else:
        updated_revision_count = 0

    # 2. Derive Canonical State
    canonical_df, raw_traces = derive_canonical_redemption_state(new_ledger_df, target_dates)
    
    # Save canonical state
    os.makedirs(os.path.dirname(canonical_csv_path), exist_ok=True)
    canonical_df.to_csv(canonical_csv_path, index=False)
    
    # 3. Compile Trace Artifact
    conflict_rows = [t for t in raw_traces if t.get("conflict_type")]
    
    # Generate daily state trace examples
    daily_state_trace_examples = []
    # Get active ledger to look up announcement/delisting dates
    active_ledger = new_ledger_df[new_ledger_df["is_active_revision"] == True] if not new_ledger_df.empty and "is_active_revision" in new_ledger_df.columns else pd.DataFrame()
    
    # Take a few examples of True risk
    risk_df = canonical_df[canonical_df["redeem_risk"] == True]
    
    # Only take up to 10 examples to avoid massive trace files
    for _, row in risk_df.head(10).iterrows():
        rep_id = row["representative_event_id"]
        rep_rev = row["representative_revision"]
        
        ann_date = ""
        del_date = ""
        if not active_ledger.empty and pd.notna(rep_id):
            mask = (active_ledger["event_id"] == rep_id) & (active_ledger["revision"] == rep_rev)
            matching = active_ledger[mask]
            if not matching.empty:
                ann_date = str(matching.iloc[0]["announcement_date"])
                del_date = str(matching.iloc[0]["delisting_date"])
                
        # Find contributing events from raw_traces if it was a coexistence case
        contributing_events = [rep_id] if pd.notna(rep_id) else []
        for t in raw_traces:
            if t["date"] == row["date"] and t["bond_code"] == row["bond_code"] and t.get("resolution_mode") == "representative_selected":
                contributing_events = t["contributing_event_ids"]
                break
                
        daily_state_trace_examples.append({
            "date": str(row["date"]),
            "bond_code": str(row["bond_code"]),
            "redeem_risk": True,
            "representative_event_id": str(rep_id) if pd.notna(rep_id) else None,
            "representative_revision": int(rep_rev) if pd.notna(rep_rev) else None,
            "contributing_event_ids": contributing_events,
            "announcement_date": ann_date,
            "delisting_date": del_date
        })
        
    trace_data = {
        "ingress_artifact_path": import_csv_path,
        "ledger_artifact_path": ledger_csv_path,
        "trace_generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted_fact_count": accepted_count,
        "rejected_fact_count": rejected_count,
        "updated_revision_count": updated_revision_count,
        "rejected_facts": rejected_facts,
        "conflict_rows": conflict_rows,
        "daily_state_trace_examples": daily_state_trace_examples
    }
    
    os.makedirs(os.path.dirname(trace_json_path), exist_ok=True)
    with open(trace_json_path, 'w', encoding='utf-8') as f:
        json.dump(trace_data, f, indent=2, ensure_ascii=False)

