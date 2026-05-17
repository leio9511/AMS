"""Pure reducer for PRD B manual redemption command logs."""

from __future__ import annotations

import os
from typing import Iterable

import pandas as pd

from etl.redemption_ledger import IMPORT_COLUMNS

COMMAND_COLUMNS = [
    "command",
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "reason",
    "created_at",
]

_REQUIRED_COLUMNS = set(COMMAND_COLUMNS)
_ALLOWED_COMMANDS = {"DECLARE", "CANCEL"}
_MANUAL_SOURCE = "manual"


def _empty_import_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=IMPORT_COLUMNS)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _missing_columns(columns: Iterable[str]) -> list[str]:
    return sorted(_REQUIRED_COLUMNS.difference(columns))


def _validate_command_row(row: pd.Series, row_number: int) -> str:
    command = _clean(row["command"]).upper()
    if command not in _ALLOWED_COMMANDS:
        raise ValueError(f"Unsupported manual command at row {row_number}: {row['command']!r}")

    source_native_event_id = _clean(row["source_native_event_id"])
    bond_code = _clean(row["bond_code"])
    announcement_date = _clean(row["announcement_date"])
    delisting_date = _clean(row["delisting_date"])
    reason = _clean(row["reason"])
    created_at = _clean(row["created_at"])

    required_values = {
        "source_native_event_id": source_native_event_id,
        "bond_code": bond_code,
        "announcement_date": announcement_date,
        "reason": reason,
        "created_at": created_at,
    }
    missing = [field for field, value in required_values.items() if not value]
    if missing:
        raise ValueError(
            f"Malformed manual command at row {row_number}: missing {', '.join(missing)}"
        )

    if command == "DECLARE" and not delisting_date:
        raise ValueError(
            f"Malformed manual DECLARE at row {row_number}: missing delisting_date"
        )

    return command


def reduce_manual_events(
    commands_df: pd.DataFrame, updated_at: str | None = None
) -> pd.DataFrame:
    """Reduce append-only DECLARE/CANCEL commands to active manual ingress facts.

    The reduction is command-log local and preserves the order supplied by
    ``commands_df``. No filesystem, ledger, canonical artifact, provider state,
    environment, or runtime clock is read by this pure reducer. When
    ``updated_at`` is not supplied, each emitted row uses the winning DECLARE
    row's ``created_at`` value as a deterministic timestamp.
    """

    missing = _missing_columns(commands_df.columns)
    if missing:
        raise ValueError(f"Manual command log missing required columns: {', '.join(missing)}")

    if commands_df.empty:
        return _empty_import_frame()

    active_by_identity: dict[str, dict[str, str]] = {}
    identity_order: list[str] = []

    for position, (_, row) in enumerate(commands_df.iterrows(), start=1):
        command = _validate_command_row(row, position)
        source_native_event_id = _clean(row["source_native_event_id"])

        if command == "DECLARE":
            if (
                source_native_event_id not in active_by_identity
                and source_native_event_id not in identity_order
            ):
                identity_order.append(source_native_event_id)
            active_by_identity[source_native_event_id] = {
                "source_native_event_id": source_native_event_id,
                "bond_code": _clean(row["bond_code"]),
                "announcement_date": _clean(row["announcement_date"]),
                "delisting_date": _clean(row["delisting_date"]),
                "source": _MANUAL_SOURCE,
                "updated_at": _clean(updated_at) or _clean(row["created_at"]),
            }
        else:
            active_by_identity.pop(source_native_event_id, None)

    rows = [active_by_identity[event_id] for event_id in identity_order if event_id in active_by_identity]
    return pd.DataFrame(rows, columns=IMPORT_COLUMNS)


def load_and_reduce_manual_events(
    path: str | os.PathLike[str], updated_at: str | None = None
) -> pd.DataFrame:
    """Read a manual command CSV, then reduce it.

    Missing command logs are valid for callers that need an absent-log adapter:
    they return an empty DataFrame with exactly ``IMPORT_COLUMNS`` and do not
    create files.
    """

    if not os.path.exists(path):
        return _empty_import_frame()
    commands_df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return reduce_manual_events(commands_df, updated_at=updated_at)
