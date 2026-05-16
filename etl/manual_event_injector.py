from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from etl.tushare_provider import IMPORT_COLUMNS

MANUAL_EVENT_COLUMNS = [
    "command",
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "reason",
    "created_at",
]
MANUAL_DECLARE = "DECLARE"
MANUAL_CANCEL = "CANCEL"
MANUAL_COMMAND_CHOICES = (MANUAL_DECLARE, MANUAL_CANCEL)
SOURCE_MANUAL = "manual"


@dataclass(frozen=True)
class ManualEventRow:
    command: str
    source_native_event_id: str
    bond_code: str
    announcement_date: str
    delisting_date: str
    reason: str
    created_at: str

    @classmethod
    def from_mapping(cls, row: dict) -> "ManualEventRow":
        normalized = {column: _normalize_scalar(row.get(column, "")) for column in MANUAL_EVENT_COLUMNS}
        command = normalize_manual_command(normalized["command"])
        return cls(
            command=command,
            source_native_event_id=normalized["source_native_event_id"],
            bond_code=normalized["bond_code"],
            announcement_date=normalized["announcement_date"],
            delisting_date=normalized["delisting_date"],
            reason=normalized["reason"],
            created_at=normalized["created_at"],
        )


def _normalize_scalar(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_manual_command(value: str) -> str:
    normalized = _normalize_scalar(value).upper()
    if normalized not in MANUAL_COMMAND_CHOICES:
        raise ValueError(f"Unsupported manual event command: {normalized}")
    return normalized


def _validate_schema(df: pd.DataFrame):
    missing_columns = [column for column in MANUAL_EVENT_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Manual events data missing required columns: " + ", ".join(missing_columns)
        )


def _validate_row(row: ManualEventRow):
    if row.command not in MANUAL_COMMAND_CHOICES:
        raise ValueError(f"Unsupported manual event command: {row.command}")
    if not row.source_native_event_id:
        raise ValueError("Manual event row missing source_native_event_id")
    if not row.reason:
        raise ValueError(
            f"Manual event row missing reason for {row.source_native_event_id}"
        )

    if row.command == MANUAL_DECLARE:
        if not row.bond_code:
            raise ValueError(
                f"DECLARE row missing bond_code for {row.source_native_event_id}"
            )
        if not row.announcement_date:
            raise ValueError(
                f"DECLARE row missing announcement_date for {row.source_native_event_id}"
            )
        if not row.delisting_date:
            raise ValueError(
                f"DECLARE row missing delisting_date for {row.source_native_event_id}"
            )
        return

    if row.delisting_date:
        raise ValueError(
            f"CANCEL row must not include delisting_date for {row.source_native_event_id}"
        )


def parse_manual_event_rows(df: pd.DataFrame) -> list[ManualEventRow]:
    if df.empty:
        _validate_schema(df)
        return []

    _validate_schema(df)
    rows = [ManualEventRow.from_mapping(record) for record in df.to_dict(orient="records")]
    for row in rows:
        _validate_row(row)
    return rows


def reduce_manual_event_rows(rows: Iterable[ManualEventRow]) -> pd.DataFrame:
    latest_by_identity: dict[str, ManualEventRow] = {}
    for row in rows:
        _validate_row(row)
        latest_by_identity[row.source_native_event_id] = row

    reduced_rows = []
    for source_native_event_id, row in latest_by_identity.items():
        if row.command != MANUAL_DECLARE:
            continue
        reduced_rows.append(
            {
                "source_native_event_id": source_native_event_id,
                "bond_code": row.bond_code,
                "announcement_date": row.announcement_date,
                "delisting_date": row.delisting_date,
                "source": SOURCE_MANUAL,
                "updated_at": row.created_at,
            }
        )

    if not reduced_rows:
        return pd.DataFrame(columns=IMPORT_COLUMNS)

    return pd.DataFrame(reduced_rows, columns=IMPORT_COLUMNS).fillna("")


def reduce_manual_events_df(df: pd.DataFrame) -> pd.DataFrame:
    rows = parse_manual_event_rows(df)
    return reduce_manual_event_rows(rows)


def load_and_reduce_manual_events(csv_path: str | Path) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Manual events file not found: {path}")

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        df = pd.DataFrame(columns=MANUAL_EVENT_COLUMNS)
    return reduce_manual_events_df(df)
