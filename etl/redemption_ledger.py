import os
from typing import Any, Dict, List, Tuple

import pandas as pd

IMPORT_COLUMNS = [
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "source",
    "updated_at",
]

REVISION_REASON_ACTIVE = "ACTIVE"
REVISION_REASON_CORRECTED = "CORRECTED"
REVISION_REASON_CANCELLED = "CANCELLED"
REVISION_REASON_SUPERSEDED = "SUPERSEDED"
REVISION_REASON_LEGACY = "LEGACY"

LEDGER_COLUMNS = [
    "event_id",
    "revision",
    "is_active_revision",
    "revision_reason",
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "source",
    "updated_at",
]


def read_import_facts(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=IMPORT_COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df


def _to_bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def _ensure_ledger_schema(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()

    for column in LEDGER_COLUMNS:
        if column not in normalized.columns:
            if column == "revision_reason":
                if "is_active_revision" in normalized.columns:
                    active_mask = _to_bool_series(normalized["is_active_revision"])
                    normalized[column] = active_mask.map(
                        {
                            True: REVISION_REASON_ACTIVE,
                            False: REVISION_REASON_LEGACY,
                        }
                    )
                else:
                    normalized[column] = ""
            else:
                normalized[column] = ""

    normalized = normalized[LEDGER_COLUMNS]

    if "revision" in normalized.columns:
        normalized["revision"] = pd.to_numeric(
            normalized["revision"], errors="coerce"
        ).fillna(0).astype(int)

    if "is_active_revision" in normalized.columns:
        normalized["is_active_revision"] = _to_bool_series(
            normalized["is_active_revision"]
        )

    return normalized


def read_ledger(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return _ensure_ledger_schema(df)


def write_ledger(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized = _ensure_ledger_schema(df)
    normalized.to_csv(path, index=False)


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


def process_ingress_to_ledger(
    ingress_df: pd.DataFrame, ledger_df: pd.DataFrame
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    rejected_facts = []

    if ledger_df.empty:
        new_ledger = pd.DataFrame(columns=LEDGER_COLUMNS)
    else:
        new_ledger = _ensure_ledger_schema(ledger_df)

    ingress_df = ingress_df.fillna("")

    new_rows = []

    max_revisions = {}
    active_states = {}
    active_in_new_rows = {}

    if not new_ledger.empty:
        max_revs = new_ledger.groupby("event_id")["revision"].max()
        for ev_id, rev in max_revs.items():
            max_revisions[ev_id] = rev

        active_mask = new_ledger["is_active_revision"] == True
        active_df = new_ledger[active_mask]
        for _, r in active_df.iterrows():
            active_states[r["event_id"]] = {
                "bond_code": str(r["bond_code"]),
                "announcement_date": str(r["announcement_date"]),
                "delisting_date": str(r["delisting_date"]),
            }

    for _, row in ingress_df.iterrows():
        is_valid, reason, event_id = _validate_and_generate_identity(row)
        if not is_valid:
            rejected_facts.append(
                {
                    "source_native_event_id": str(row.get("source_native_event_id", "")),
                    "bond_code": str(row.get("bond_code", "")),
                    "reason": reason,
                    "source": str(row.get("source", "")),
                }
            )
            continue

        bus_fields = ["bond_code", "announcement_date", "delisting_date"]
        current_state = {f: str(row[f]) for f in bus_fields}

        if event_id not in max_revisions:
            new_row = {
                "event_id": event_id,
                "revision": 0,
                "is_active_revision": True,
                "revision_reason": REVISION_REASON_ACTIVE,
                "source_native_event_id": row["source_native_event_id"],
                "bond_code": row["bond_code"],
                "announcement_date": row["announcement_date"],
                "delisting_date": row["delisting_date"],
                "source": row["source"],
                "updated_at": row["updated_at"],
            }
            new_rows.append(new_row)
            max_revisions[event_id] = 0
            active_states[event_id] = current_state
            active_in_new_rows[event_id] = len(new_rows) - 1
        else:
            active_state = active_states.get(event_id)
            if active_state:
                is_duplicate = all(
                    active_state[field] == current_state[field] for field in bus_fields
                )
                if not is_duplicate:
                    if event_id in active_in_new_rows:
                        idx = active_in_new_rows[event_id]
                        new_rows[idx]["is_active_revision"] = False
                        new_rows[idx]["revision_reason"] = REVISION_REASON_CORRECTED
                    else:
                        mask = (
                            (new_ledger["event_id"] == event_id)
                            & (new_ledger["is_active_revision"] == True)
                        )
                        new_ledger.loc[mask, "is_active_revision"] = False
                        new_ledger.loc[mask, "revision_reason"] = (
                            REVISION_REASON_CORRECTED
                        )

                    prev_max_revision = max_revisions[event_id]
                    new_row = {
                        "event_id": event_id,
                        "revision": prev_max_revision + 1,
                        "is_active_revision": True,
                        "revision_reason": REVISION_REASON_ACTIVE,
                        "source_native_event_id": row["source_native_event_id"],
                        "bond_code": row["bond_code"],
                        "announcement_date": row["announcement_date"],
                        "delisting_date": row["delisting_date"],
                        "source": row["source"],
                        "updated_at": row["updated_at"],
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
                    "revision_reason": REVISION_REASON_ACTIVE,
                    "source_native_event_id": row["source_native_event_id"],
                    "bond_code": row["bond_code"],
                    "announcement_date": row["announcement_date"],
                    "delisting_date": row["delisting_date"],
                    "source": row["source"],
                    "updated_at": row["updated_at"],
                }
                new_rows.append(new_row)
                max_revisions[event_id] = prev_max_revision + 1
                active_states[event_id] = current_state
                active_in_new_rows[event_id] = len(new_rows) - 1

    if new_rows:
        new_ledger = pd.concat([new_ledger, pd.DataFrame(new_rows)], ignore_index=True)

    if not new_ledger.empty:
        new_ledger = _ensure_ledger_schema(new_ledger)

    return new_ledger, rejected_facts
