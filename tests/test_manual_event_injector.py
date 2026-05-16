from pathlib import Path

import pandas as pd
import pytest

from etl.manual_event_injector import (
    MANUAL_EVENT_COLUMNS,
    SOURCE_MANUAL,
    load_and_reduce_manual_events,
    reduce_manual_events_df,
)
from etl.tushare_provider import IMPORT_COLUMNS


def _manual_events_df(rows):
    return pd.DataFrame(rows, columns=MANUAL_EVENT_COLUMNS)


def test_reduce_manual_events_df_emits_one_manual_row_when_identity_history_ends_in_declare():
    reduced = reduce_manual_events_df(
        _manual_events_df(
            [
                {
                    "command": "DECLARE",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "reason": "TuShare unavailable",
                    "created_at": "2026-05-15T10:00:00Z",
                }
            ]
        )
    )

    assert len(reduced) == 1
    assert list(reduced.columns) == IMPORT_COLUMNS
    row = reduced.iloc[0]
    assert row["source_native_event_id"] == "110001SH_20260515"
    assert row["bond_code"] == "110001.SH"
    assert row["announcement_date"] == "2026-05-15"
    assert row["delisting_date"] == "2026-06-20"
    assert row["source"] == SOURCE_MANUAL
    assert row["updated_at"] == "2026-05-15T10:00:00Z"


def test_reduce_manual_events_df_drops_identity_when_latest_effective_command_is_cancel():
    reduced = reduce_manual_events_df(
        _manual_events_df(
            [
                {
                    "command": "DECLARE",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "reason": "Initial declaration",
                    "created_at": "2026-05-15T10:00:00Z",
                },
                {
                    "command": "CANCEL",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "",
                    "reason": "Wrong manual entry",
                    "created_at": "2026-05-15T11:00:00Z",
                },
            ]
        )
    )

    assert reduced.empty
    assert list(reduced.columns) == IMPORT_COLUMNS


def test_reduce_manual_events_df_latest_redeclare_wins_after_prior_cancel():
    reduced = reduce_manual_events_df(
        _manual_events_df(
            [
                {
                    "command": "DECLARE",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "reason": "Initial declaration",
                    "created_at": "2026-05-15T10:00:00Z",
                },
                {
                    "command": "CANCEL",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "",
                    "reason": "Correcting typo",
                    "created_at": "2026-05-15T11:00:00Z",
                },
                {
                    "command": "DECLARE",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-16",
                    "delisting_date": "2026-06-25",
                    "reason": "Re-declared with corrected payload",
                    "created_at": "2026-05-15T12:00:00Z",
                },
            ]
        )
    )

    assert len(reduced) == 1
    row = reduced.iloc[0]
    assert row["announcement_date"] == "2026-05-16"
    assert row["delisting_date"] == "2026-06-25"
    assert row["updated_at"] == "2026-05-15T12:00:00Z"


def test_reduce_manual_events_df_ignores_cancel_only_history_without_emitting_tombstone_rows():
    reduced = reduce_manual_events_df(
        _manual_events_df(
            [
                {
                    "command": "CANCEL",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "",
                    "reason": "Orphan cancellation tolerated",
                    "created_at": "2026-05-15T11:00:00Z",
                }
            ]
        )
    )

    assert reduced.empty
    assert list(reduced.columns) == IMPORT_COLUMNS


def test_load_and_reduce_manual_events_preserves_import_column_order_and_manual_source_marker(tmp_path):
    manual_events_path = tmp_path / "manual_events.csv"
    manual_events_path.write_text(
        "\n".join(
            [
                "command,source_native_event_id,bond_code,announcement_date,delisting_date,reason,created_at",
                "DECLARE,110001SH_20260515,110001.SH,2026-05-15,2026-06-20,TuShare unavailable,2026-05-15T10:00:00Z",
                "DECLARE,127001SZ_20260515,127001.SZ,2026-05-15,2026-06-22,Will be canceled,2026-05-15T10:05:00Z",
                "CANCEL,127001SZ_20260515,127001.SZ,2026-05-15,,Wrong manual entry,2026-05-15T10:10:00Z",
            ]
        ),
        encoding="utf-8",
    )

    reduced = load_and_reduce_manual_events(manual_events_path)

    assert list(reduced.columns) == IMPORT_COLUMNS
    assert reduced["source"].tolist() == [SOURCE_MANUAL]
    assert reduced["source_native_event_id"].tolist() == ["110001SH_20260515"]


def test_reduce_multiple_identities_isolated_by_source_native_event_id():
    reduced = reduce_manual_events_df(
        _manual_events_df(
            [
                {
                    "command": "DECLARE",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "reason": "Keep active",
                    "created_at": "2026-05-15T10:00:00Z",
                },
                {
                    "command": "DECLARE",
                    "source_native_event_id": "127001SZ_20260515",
                    "bond_code": "127001.SZ",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-22",
                    "reason": "Will be canceled",
                    "created_at": "2026-05-15T10:05:00Z",
                },
                {
                    "command": "CANCEL",
                    "source_native_event_id": "127001SZ_20260515",
                    "bond_code": "127001.SZ",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "",
                    "reason": "Cancel second identity only",
                    "created_at": "2026-05-15T10:10:00Z",
                },
            ]
        )
    )

    assert reduced["source_native_event_id"].tolist() == ["110001SH_20260515"]
    assert reduced.iloc[0]["bond_code"] == "110001.SH"


def test_manual_reducer_output_matches_import_column_contract():
    reduced = reduce_manual_events_df(
        _manual_events_df(
            [
                {
                    "command": "DECLARE",
                    "source_native_event_id": "110001SH_20260515",
                    "bond_code": "110001.SH",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "reason": "Contract match",
                    "created_at": "2026-05-15T10:00:00Z",
                }
            ]
        )
    )

    assert list(reduced.columns) == IMPORT_COLUMNS


def test_manual_events_seed_file_has_exact_required_header():
    manual_events_path = Path("data/manual_events.csv")

    if not manual_events_path.exists():
        # The seed file belongs to a separate manual-command-log slice, so keep this reducer PR resilient
        # while still verifying the header when that file is present in the repo state under test.
        pytest.skip("manual_events.csv seed file is not part of this reducer-focused PR slice")

    header = manual_events_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "command,source_native_event_id,bond_code,announcement_date,delisting_date,reason,created_at"

    reduced = load_and_reduce_manual_events(manual_events_path)
    assert reduced.empty
    assert list(reduced.columns) == IMPORT_COLUMNS
