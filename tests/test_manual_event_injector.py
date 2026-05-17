import os

import pandas as pd
import pytest

from etl import redemption_ledger
from etl.manual_event_injector import load_and_reduce_manual_events, reduce_manual_events


COMMAND_COLUMNS = [
    "command",
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "reason",
    "created_at",
]


def commands(*rows):
    return pd.DataFrame(rows, columns=COMMAND_COLUMNS)


def declare(
    native_id="123456.SH_2026-05-15",
    bond="123456.SH",
    ann="2026-05-15",
    delist="2026-06-20",
    reason="TuShare API unavailable",
    created="2026-05-15T10:00:00Z",
    command="DECLARE",
):
    return [command, native_id, bond, ann, delist, reason, created]


def cancel(
    native_id="123456.SH_2026-05-15",
    bond="123456.SH",
    ann="2026-05-15",
    reason="wrong manual entry",
    created="2026-05-15T11:00:00Z",
    command="CANCEL",
):
    return [command, native_id, bond, ann, "", reason, created]


def assert_import_schema(df):
    assert list(df.columns) == redemption_ledger.IMPORT_COLUMNS


def test_reduce_declare_only_emits_one_manual_import_row():
    result = reduce_manual_events(
        commands(declare()), updated_at="2026-05-15T12:00:00Z"
    )

    assert_import_schema(result)
    assert len(result) == 1
    row = result.iloc[0].to_dict()
    assert row == {
        "source_native_event_id": "123456.SH_2026-05-15",
        "bond_code": "123456.SH",
        "announcement_date": "2026-05-15",
        "delisting_date": "2026-06-20",
        "source": "manual",
        "updated_at": "2026-05-15T12:00:00Z",
    }


def test_reduce_declare_then_cancel_emits_no_rows():
    result = reduce_manual_events(commands(declare(), cancel()))

    assert result.empty
    assert_import_schema(result)


def test_reduce_declare_cancel_declare_latest_declare_wins():
    result = reduce_manual_events(
        commands(
            declare(delist="2026-06-20", created="2026-05-15T10:00:00Z"),
            cancel(created="2026-05-15T11:00:00Z"),
            declare(delist="2026-07-01", created="2026-05-15T12:00:00Z"),
        )
    )

    assert_import_schema(result)
    assert len(result) == 1
    assert result.iloc[0]["delisting_date"] == "2026-07-01"
    assert result.iloc[0]["updated_at"] == "2026-05-15T12:00:00Z"
    assert result.iloc[0]["source"] == "manual"


def test_reduce_cancel_without_prior_declare_is_empty_not_error():
    result = reduce_manual_events(commands(cancel()))

    assert result.empty
    assert_import_schema(result)


def test_reduce_multiple_identities_independently():
    result = reduce_manual_events(
        commands(
            declare(
                native_id="123456.SH_2026-05-15",
                bond="123456.SH",
                ann="2026-05-15",
                delist="2026-06-20",
            ),
            declare(
                native_id="654321.SH_2026-05-15",
                bond="654321.SH",
                ann="2026-05-15",
                delist="2026-06-25",
            ),
            cancel(
                native_id="123456.SH_2026-05-15",
                bond="123456.SH",
                ann="2026-05-15",
            ),
        ),
        updated_at="2026-05-15T13:00:00Z",
    )

    assert_import_schema(result)
    assert result.to_dict("records") == [
        {
            "source_native_event_id": "654321.SH_2026-05-15",
            "bond_code": "654321.SH",
            "announcement_date": "2026-05-15",
            "delisting_date": "2026-06-25",
            "source": "manual",
            "updated_at": "2026-05-15T13:00:00Z",
        }
    ]


def test_reducer_rejects_unknown_command_and_missing_required_fields():
    invalid_cases = [
        commands(declare(command="UPDATE")),
        commands(declare(bond="")),
        commands(declare(ann="")),
        commands(declare(delist="")),
    ]

    for invalid in invalid_cases:
        with pytest.raises(ValueError):
            reduce_manual_events(invalid)


def test_reducer_is_pure_no_filesystem_ledger_or_clock_dependency(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("pure reducer must not access filesystem")

    monkeypatch.setattr(os.path, "exists", fail_if_called)

    result = reduce_manual_events(
        commands(declare(created="1999-01-01T00:00:00Z")),
        updated_at="2026-05-15T14:00:00Z",
    )

    assert_import_schema(result)
    assert result.iloc[0]["updated_at"] == "2026-05-15T14:00:00Z"


def test_load_and_reduce_absent_command_log_returns_empty_import_schema_if_helper_exists(tmp_path):
    missing_path = tmp_path / "manual_events.csv"

    result = load_and_reduce_manual_events(missing_path, updated_at="2026-05-15T14:00:00Z")

    assert result.empty
    assert_import_schema(result)
    assert not missing_path.exists()


def test_reducer_does_not_emit_tombstone_or_supersede_columns():
    result = reduce_manual_events(commands(declare()))

    assert_import_schema(result)
    forbidden_columns = {
        "revision_reason",
        "event_id",
        "SUPERSEDED",
        "tombstone",
        "takeover",
        "is_active_revision",
        "revision",
    }
    assert forbidden_columns.isdisjoint(result.columns)
