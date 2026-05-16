import csv
import subprocess
import sys
from pathlib import Path

import pytest

from etl.manual_event_injector import MANUAL_COMMAND_CHOICES
from scripts.manual_redemption_inject import append_manual_command

HEADER = "command,source_native_event_id,bond_code,announcement_date,delisting_date,reason,created_at\n"


def _seed_manual_events_csv(path: Path, body: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + body, encoding="utf-8")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _base_args(csv_path: Path, command: str = "DECLARE") -> list[str]:
    args = [
        "--command",
        command,
        "--bond",
        "123456.SH",
        "--ann",
        "2026-05-15",
        "--reason",
        "TuShare API unavailable",
        "--source-native-event-id",
        "123456.SH_2026-05-15",
        "--csv-path",
        str(csv_path),
    ]
    if command.upper() == "DECLARE":
        args.extend(["--delist", "2026-06-20"])
    return args


def test_cli_appends_single_declare_row_with_created_at_timestamp(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)

    append_manual_command(_base_args(csv_path), created_at="2026-05-15T10:00:00Z")

    rows = _read_rows(csv_path)
    assert len(rows) == 1
    assert rows[0] == {
        "command": "DECLARE",
        "source_native_event_id": "123456.SH_2026-05-15",
        "bond_code": "123456.SH",
        "announcement_date": "2026-05-15",
        "delisting_date": "2026-06-20",
        "reason": "TuShare API unavailable",
        "created_at": "2026-05-15T10:00:00Z",
    }


def test_cli_initializes_missing_csv_with_header_before_appending_first_row(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"

    append_manual_command(_base_args(csv_path), created_at="2026-05-15T10:00:00Z")

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == HEADER.rstrip("\n")
    rows = _read_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["command"] == "DECLARE"


def test_cli_appends_single_cancel_row_with_empty_delisting_date(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)

    append_manual_command(
        _base_args(csv_path, command="CANCEL"),
        created_at="2026-05-15T11:00:00Z",
    )

    rows = _read_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["command"] == "CANCEL"
    assert rows[0]["delisting_date"] == ""
    assert rows[0]["created_at"] == "2026-05-15T11:00:00Z"


def test_cli_rejects_declare_without_delist(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)
    before = csv_path.read_text(encoding="utf-8")
    args = _base_args(csv_path)
    del args[args.index("--delist") : args.index("--delist") + 2]

    with pytest.raises(ValueError, match="--delist is required"):
        append_manual_command(args, created_at="2026-05-15T10:00:00Z")

    assert csv_path.read_text(encoding="utf-8") == before


def test_cli_rejects_cancel_with_delist_value(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)
    before = csv_path.read_text(encoding="utf-8")
    args = _base_args(csv_path, command="CANCEL") + ["--delist", "2026-06-20"]

    with pytest.raises(ValueError, match="--delist must be omitted for CANCEL"):
        append_manual_command(args, created_at="2026-05-15T10:00:00Z")

    assert csv_path.read_text(encoding="utf-8") == before


def test_cli_requires_reason_and_source_native_event_id(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)
    before = csv_path.read_text(encoding="utf-8")

    with pytest.raises(SystemExit):
        append_manual_command(
            [
                "--command",
                "DECLARE",
                "--bond",
                "123456.SH",
                "--ann",
                "2026-05-15",
                "--delist",
                "2026-06-20",
                "--csv-path",
                str(csv_path),
            ],
            created_at="2026-05-15T10:00:00Z",
        )

    assert csv_path.read_text(encoding="utf-8") == before


def test_cli_preserves_existing_rows_and_appends_only_one_new_row(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    existing_row = (
        "DECLARE,110001.SH_2026-05-14,110001.SH,2026-05-14,2026-06-15,existing row,2026-05-14T09:00:00Z\n"
    )
    _seed_manual_events_csv(csv_path, body=existing_row)
    before = csv_path.read_text(encoding="utf-8")

    append_manual_command(_base_args(csv_path), created_at="2026-05-15T10:00:00Z")

    after = csv_path.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert after == before + (
        "DECLARE,123456.SH_2026-05-15,123456.SH,2026-05-15,2026-06-20,TuShare API unavailable,2026-05-15T10:00:00Z\n"
    )


def test_cli_normalizes_command_casing_to_uppercase_enum(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)

    append_manual_command(
        _base_args(csv_path, command="declare"),
        created_at="2026-05-15T10:00:00Z",
    )

    rows = _read_rows(csv_path)
    assert rows[0]["command"] == "DECLARE"


def test_cli_rejects_invalid_command_enum(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)
    before = csv_path.read_text(encoding="utf-8")
    args = _base_args(csv_path, command="INVALID")

    with pytest.raises(
        ValueError,
        match=f"--command must be {'|'.join(MANUAL_COMMAND_CHOICES)}".replace("|", " or "),
    ):
        append_manual_command(args, created_at="2026-05-15T10:00:00Z")

    assert csv_path.read_text(encoding="utf-8") == before


def test_cli_script_runs_via_direct_python_invocation(tmp_path):
    csv_path = tmp_path / "data" / "manual_events.csv"
    _seed_manual_events_csv(csv_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/manual_redemption_inject.py",
            * _base_args(csv_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    rows = _read_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["command"] == "DECLARE"
