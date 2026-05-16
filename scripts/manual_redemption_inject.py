from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.manual_event_injector import (
    MANUAL_CANCEL,
    MANUAL_COMMAND_CHOICES,
    MANUAL_DECLARE,
    MANUAL_EVENT_COLUMNS,
    normalize_manual_command,
)

DEFAULT_MANUAL_EVENTS_PATH = PROJECT_ROOT / "data" / "manual_events.csv"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append one validated manual redemption command to the manual event log.",
    )
    parser.add_argument("--command", required=True)
    parser.add_argument("--bond", required=True)
    parser.add_argument("--ann", required=True)
    parser.add_argument("--delist")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--source-native-event-id", dest="source_native_event_id", required=True)
    parser.add_argument(
        "--csv-path",
        default=str(DEFAULT_MANUAL_EVENTS_PATH),
        help="Path to manual_events.csv for testing or alternate environments.",
    )
    return parser.parse_args(argv)


def _normalize_text(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def _normalize_command(value: str) -> str:
    try:
        return normalize_manual_command(value)
    except ValueError as exc:
        raise ValueError(
            f"--command must be {' or '.join(MANUAL_COMMAND_CHOICES)}"
        ) from exc


def _validate_date_arg(flag_name: str, value: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError(f"{flag_name} is required")
    try:
        datetime.strptime(normalized, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{flag_name} must be in YYYY-MM-DD format") from exc
    return normalized


def _created_at_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_row(args: argparse.Namespace, created_at: str | None = None) -> dict[str, str]:
    command = _normalize_command(args.command)
    bond_code = _normalize_text(args.bond)
    announcement_date = _validate_date_arg("--ann", args.ann)
    reason = _normalize_text(args.reason)
    source_native_event_id = _normalize_text(args.source_native_event_id)
    delisting_date = _normalize_text(args.delist)

    if not bond_code:
        raise ValueError("--bond is required")
    if not reason:
        raise ValueError("--reason is required")
    if not source_native_event_id:
        raise ValueError("--source-native-event-id is required")

    if command == MANUAL_DECLARE:
        delisting_date = _validate_date_arg("--delist", delisting_date)
    elif delisting_date:
        raise ValueError("--delist must be omitted for CANCEL")

    row = {
        "command": command,
        "source_native_event_id": source_native_event_id,
        "bond_code": bond_code,
        "announcement_date": announcement_date,
        "delisting_date": delisting_date,
        "reason": reason,
        "created_at": created_at or _created_at_now(),
    }
    return row


def _read_and_validate_header(csv_path: Path) -> list[str]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Manual events file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Manual events file is empty: {csv_path}") from exc

    if header != MANUAL_EVENT_COLUMNS:
        raise ValueError(
            "Manual events file header mismatch. Expected: "
            + ",".join(MANUAL_EVENT_COLUMNS)
        )
    return header


def append_manual_command(
    argv: Sequence[str] | None = None,
    *,
    created_at: str | None = None,
) -> dict[str, str]:
    args = _parse_args(argv)
    csv_path = Path(args.csv_path)
    _read_and_validate_header(csv_path)
    row = _build_row(args, created_at=created_at)

    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANUAL_EVENT_COLUMNS)
        writer.writerow(row)

    return row


def main(argv: Sequence[str] | None = None) -> int:
    append_manual_command(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
