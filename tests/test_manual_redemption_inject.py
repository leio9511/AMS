import csv
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manual_redemption_inject.py"
HEADER = [
    "command",
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "reason",
    "created_at",
]
HEADER_LINE = ",".join(HEADER) + "\n"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("manual_redemption_inject", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = load_cli_module()
    monkeypatch.setattr(module, "utc_now_iso", lambda: "2026-05-17T10:00:00Z")
    return module


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_ok(cli, args):
    assert cli.main(args) == 0


def run_bad(cli, args):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(args)
    assert exc_info.value.code != 0


def test_declare_appends_one_row_and_preserves_history(cli):
    events_path = Path("data/manual_events.csv")
    events_path.parent.mkdir(parents=True)
    prior = (
        HEADER_LINE
        + "DECLARE,OLD_ID,110001.SH,2026-05-16,2026-06-16,prior reason,2026-05-16T00:00:00Z\n"
    )
    events_path.write_text(prior, encoding="utf-8")
    prior_bytes = events_path.read_bytes()

    run_ok(
        cli,
        [
            "--command",
            "declare",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--delist",
            "2026-06-20",
            "--reason",
            "TuShare unavailable",
        ],
    )

    after_bytes = events_path.read_bytes()
    assert after_bytes.startswith(prior_bytes)
    rows = read_rows(events_path)
    assert len(rows) == 2
    assert rows[0]["source_native_event_id"] == "OLD_ID"
    assert rows[1] == {
        "command": "DECLARE",
        "source_native_event_id": "123456.SH_2026-05-17",
        "bond_code": "123456.SH",
        "announcement_date": "2026-05-17",
        "delisting_date": "2026-06-20",
        "reason": "TuShare unavailable",
        "created_at": "2026-05-17T10:00:00Z",
    }


def test_cancel_appends_empty_delisting_date_for_same_derived_identity(cli):
    events_path = Path("data/manual_events.csv")
    run_ok(
        cli,
        [
            "--command",
            "DECLARE",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--delist",
            "2026-06-20",
            "--reason",
            "initial manual fact",
        ],
    )
    prior_bytes = events_path.read_bytes()

    run_ok(
        cli,
        [
            "--command",
            "cancel",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--reason",
            "wrong manual entry",
        ],
    )

    assert events_path.read_bytes().startswith(prior_bytes)
    rows = read_rows(events_path)
    assert len(rows) == 2
    assert rows[0]["source_native_event_id"] == rows[1]["source_native_event_id"]
    assert rows[1]["command"] == "CANCEL"
    assert rows[1]["source_native_event_id"] == "123456.SH_2026-05-17"
    assert rows[1]["delisting_date"] == ""
    assert rows[1]["reason"] == "wrong manual entry"


def test_cli_rejects_operator_supplied_identity_argument(cli):
    run_bad(
        cli,
        [
            "--command",
            "DECLARE",
            "--source-native-event-id",
            "OPERATOR_ID",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--delist",
            "2026-06-20",
            "--reason",
            "not allowed",
        ],
    )
    assert not Path("data/manual_events.csv").exists()


def test_declare_and_cancel_field_validation(cli):
    invalid_invocations = [
        ["--command", "DECLARE", "--bond", "123456.SH", "--ann", "2026-05-17", "--reason", "missing delist"],
        [
            "--command",
            "CANCEL",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--delist",
            "2026-06-20",
            "--reason",
            "delist forbidden",
        ],
        ["--command", "DECLARE", "--bond", "123456.SH", "--ann", "2026-05-17", "--delist", "2026-06-20", "--reason", "  "],
        ["--command", "REVOKE", "--bond", "123456.SH", "--ann", "2026-05-17", "--reason", "bad command"],
        ["--command", "DECLARE", "--bond", "123456.SH", "--ann", "20260517", "--delist", "2026-06-20", "--reason", "bad ann"],
        ["--command", "DECLARE", "--bond", "123456.SH", "--ann", "2026-05-17", "--delist", "20260620", "--reason", "bad delist"],
    ]

    for args in invalid_invocations:
        run_bad(cli, args)

    assert not Path("data/manual_events.csv").exists()


def test_cli_creates_manual_events_header_when_missing(cli):
    events_path = Path("data/manual_events.csv")

    run_ok(
        cli,
        [
            "--command",
            "DECLARE",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--delist",
            "2026-06-20",
            "--reason",
            "TuShare unavailable",
        ],
    )

    text = events_path.read_text(encoding="utf-8")
    assert text.startswith(HEADER_LINE)
    rows = read_rows(events_path)
    assert len(rows) == 1
    assert rows[0]["command"] == "DECLARE"


def test_completion_signal_records_zero_row_review_without_event_row(cli):
    completions_path = Path("data/manual_review_completions.json")

    run_ok(
        cli,
        [
            "--complete-review",
            "--ann",
            "2026-05-17",
            "--reason",
            "reviewed exchange announcements; no redemption events",
        ],
    )

    assert not Path("data/manual_events.csv").exists()
    payload = json.loads(completions_path.read_text(encoding="utf-8"))
    assert payload == [
        {
            "announcement_date": "2026-05-17",
            "created_at": "2026-05-17T10:00:00Z",
            "reason": "reviewed exchange announcements; no redemption events",
        }
    ]
    assert "NO_EVENTS" not in completions_path.read_text(encoding="utf-8")


def test_completion_signal_requires_target_date_and_reason(cli):
    invalid_invocations = [
        ["--complete-review", "--reason", "missing date"],
        ["--complete-review", "--ann", "20260517", "--reason", "bad date"],
        ["--complete-review", "--ann", "2026-05-17", "--reason", " "],
    ]

    for args in invalid_invocations:
        run_bad(cli, args)

    assert not Path("data/manual_events.csv").exists()
    assert not Path("data/manual_review_completions.json").exists()


def test_manual_cli_does_not_import_or_call_ledger_or_provider_modules(cli, monkeypatch):
    import builtins

    blocked = {
        "etl.redemption_ledger",
        "etl.redemption_fetcher",
        "etl.tushare_provider",
        "tushare",
    }
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in blocked or any(name.startswith(f"{blocked_name}.") for blocked_name in blocked):
            raise AssertionError(f"manual CLI must not import {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    run_ok(
        cli,
        [
            "--command",
            "DECLARE",
            "--bond",
            "123456.SH",
            "--ann",
            "2026-05-17",
            "--delist",
            "2026-06-20",
            "--reason",
            "thin writer only",
        ],
    )

    rows = read_rows(Path("data/manual_events.csv"))
    assert rows[0]["source_native_event_id"] == "123456.SH_2026-05-17"
