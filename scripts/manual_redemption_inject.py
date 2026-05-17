#!/usr/bin/env python3
"""Append-only manual redemption command-log CLI for PRD B.

Identity rule: source_native_event_id is derived deterministically as
"{bond_code}_{announcement_date}" from exactly the operator supplied bond code and
announcement date. Operators must not supply identity directly.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

MANUAL_EVENTS_PATH = Path("data/manual_events.csv")
COMPLETIONS_PATH = Path("data/manual_review_completions.json")
HEADER = [
    "command",
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "reason",
    "created_at",
]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_date(value: str, field_name: str, parser: argparse.ArgumentParser) -> str:
    if not value or not DATE_RE.match(value):
        parser.error(f"{field_name} must be in YYYY-MM-DD format")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        parser.error(f"{field_name} must be a valid YYYY-MM-DD date")
    return value


def require_non_blank(value: str | None, field_name: str, parser: argparse.ArgumentParser) -> str:
    if value is None or not value.strip():
        parser.error(f"{field_name} is required and must be non-empty")
    return value.strip()


def derive_source_native_event_id(bond_code: str, announcement_date: str) -> str:
    return f"{bond_code}_{announcement_date}"


def ensure_manual_events_header(path: Path = MANUAL_EVENTS_PATH) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)


def append_event_row(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    command = require_non_blank(args.command, "--command", parser).upper()
    if command not in {"DECLARE", "CANCEL"}:
        parser.error("--command must be DECLARE or CANCEL")

    bond_code = require_non_blank(args.bond, "--bond", parser)
    announcement_date = validate_date(require_non_blank(args.ann, "--ann", parser), "--ann", parser)
    reason = require_non_blank(args.reason, "--reason", parser)

    delisting_date = ""
    if command == "DECLARE":
        delisting_date = validate_date(require_non_blank(args.delist, "--delist", parser), "--delist", parser)
    elif args.delist is not None and args.delist.strip():
        parser.error("--delist is forbidden for CANCEL")

    ensure_manual_events_header(MANUAL_EVENTS_PATH)
    row = [
        command,
        derive_source_native_event_id(bond_code, announcement_date),
        bond_code,
        announcement_date,
        delisting_date,
        reason,
        utc_now_iso(),
    ]
    with MANUAL_EVENTS_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(row)
    return 0


def record_completion(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    announcement_date = validate_date(require_non_blank(args.ann, "--ann", parser), "--ann", parser)
    reason = require_non_blank(args.reason, "--reason", parser)
    payload = []
    if COMPLETIONS_PATH.exists():
        with COMPLETIONS_PATH.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if not isinstance(existing, list):
            parser.error(f"{COMPLETIONS_PATH} must contain a JSON list")
        payload = existing

    payload.append(
        {
            "announcement_date": announcement_date,
            "created_at": utc_now_iso(),
            "reason": reason,
        }
    )
    COMPLETIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COMPLETIONS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append manual redemption DECLARE/CANCEL commands.")
    parser.add_argument("--complete-review", action="store_true", help="Record explicit target-date manual review completion without appending an event row.")
    parser.add_argument("--command", help="DECLARE or CANCEL for event-bearing rows.")
    parser.add_argument("--bond", help="Bond code for event-bearing rows.")
    parser.add_argument("--ann", help="Announcement/target date in YYYY-MM-DD format.")
    parser.add_argument("--delist", help="Delisting date in YYYY-MM-DD format; required for DECLARE and forbidden for CANCEL.")
    parser.add_argument("--reason", help="Non-empty operator reason/note.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.complete_review:
        if args.command or args.bond or args.delist:
            parser.error("--complete-review only accepts --ann and --reason")
        return record_completion(args, parser)
    return append_event_row(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
