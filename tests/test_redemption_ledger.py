import pandas as pd

from etl.redemption_ledger import (
    LEDGER_COLUMNS,
    REVISION_REASON_ACTIVE,
    REVISION_REASON_CORRECTED,
    REVISION_REASON_LEGACY,
    process_ingress_to_ledger,
    read_ledger,
    write_ledger,
)


def _ingress_row(
    source_native_event_id: str,
    bond_code: str = "110001",
    announcement_date: str = "2023-01-01",
    delisting_date: str = "2023-01-10",
    source: str = "srcA",
    updated_at: str = "2023-01-01T00:00:00Z",
):
    return {
        "source_native_event_id": source_native_event_id,
        "bond_code": bond_code,
        "announcement_date": announcement_date,
        "delisting_date": delisting_date,
        "source": source,
        "updated_at": updated_at,
    }


def test_event_identity_authority():
    ingress_df = pd.DataFrame(
        [
            _ingress_row("123"),
            _ingress_row("", bond_code="110002"),
        ]
    )
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger, rejected = process_ingress_to_ledger(ingress_df, ledger_df)

    assert len(new_ledger) == 1
    assert new_ledger.iloc[0]["event_id"] == "srcA:123"

    assert len(rejected) == 1
    assert rejected[0]["reason"] == "MISSING_SOURCE_NATIVE_EVENT_ID"
    assert rejected[0]["source_native_event_id"] == ""


def test_new_event_rows_are_written_with_active_revision_reason():
    ingress_df = pd.DataFrame([_ingress_row("123")])
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger, rejected = process_ingress_to_ledger(ingress_df, ledger_df)

    assert len(new_ledger) == 1
    assert len(rejected) == 0

    row = new_ledger.iloc[0]
    assert row["event_id"] == "srcA:123"
    assert row["revision"] == 0
    assert bool(row["is_active_revision"]) is True
    assert row["revision_reason"] == REVISION_REASON_ACTIVE


def test_correction_marks_previous_revision_corrected_and_new_revision_active():
    original_ingress_df = pd.DataFrame([_ingress_row("123")])
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)
    first_ledger, _ = process_ingress_to_ledger(original_ingress_df, ledger_df)

    corrected_ingress_df = pd.DataFrame(
        [
            _ingress_row(
                "123",
                delisting_date="2023-01-15",
                updated_at="2023-01-02T00:00:00Z",
            )
        ]
    )
    second_ledger, rejected = process_ingress_to_ledger(corrected_ingress_df, first_ledger)

    assert len(rejected) == 0
    assert len(second_ledger) == 2

    rev0 = second_ledger[second_ledger["revision"] == 0].iloc[0]
    rev1 = second_ledger[second_ledger["revision"] == 1].iloc[0]

    assert bool(rev0["is_active_revision"]) is False
    assert rev0["revision_reason"] == REVISION_REASON_CORRECTED
    assert bool(rev1["is_active_revision"]) is True
    assert rev1["revision_reason"] == REVISION_REASON_ACTIVE
    assert rev1["delisting_date"] == "2023-01-15"


def test_duplicate_ingress_remains_idempotent_without_revision_reason_churn():
    ingress_df = pd.DataFrame([_ingress_row("123")])
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    first_ledger, _ = process_ingress_to_ledger(ingress_df, ledger_df)
    second_ledger, rejected = process_ingress_to_ledger(ingress_df, first_ledger)

    assert len(rejected) == 0
    assert len(second_ledger) == 1

    row = second_ledger.iloc[0]
    assert row["revision"] == 0
    assert bool(row["is_active_revision"]) is True
    assert row["revision_reason"] == REVISION_REASON_ACTIVE


def test_read_ledger_backfills_revision_reason_for_legacy_files_missing_the_column(tmp_path):
    ledger_path = tmp_path / "legacy_ledger.csv"
    legacy_df = pd.DataFrame(
        [
            {
                "event_id": "srcA:123",
                "revision": 0,
                "is_active_revision": True,
                "source_native_event_id": "123",
                "bond_code": "110001",
                "announcement_date": "2023-01-01",
                "delisting_date": "2023-01-10",
                "source": "srcA",
                "updated_at": "2023-01-01T00:00:00Z",
            },
            {
                "event_id": "srcA:123",
                "revision": 1,
                "is_active_revision": False,
                "source_native_event_id": "123",
                "bond_code": "110001",
                "announcement_date": "2023-01-01",
                "delisting_date": "2023-01-15",
                "source": "srcA",
                "updated_at": "2023-01-02T00:00:00Z",
            },
        ]
    )
    legacy_df.to_csv(ledger_path, index=False)

    loaded = read_ledger(str(ledger_path))

    assert list(loaded.columns) == LEDGER_COLUMNS
    assert loaded["revision"].tolist() == [0, 1]
    assert loaded["is_active_revision"].tolist() == [True, False]
    assert loaded["revision_reason"].tolist() == [
        REVISION_REASON_ACTIVE,
        REVISION_REASON_LEGACY,
    ]


def test_read_ledger_preserves_existing_revision_reason_values_when_column_already_exists(tmp_path):
    ledger_path = tmp_path / "modern_ledger.csv"
    original_df = pd.DataFrame(
        [
            {
                "event_id": "srcA:123",
                "revision": 0,
                "is_active_revision": True,
                "revision_reason": REVISION_REASON_ACTIVE,
                "source_native_event_id": "123",
                "bond_code": "110001",
                "announcement_date": "2023-01-01",
                "delisting_date": "2023-01-10",
                "source": "srcA",
                "updated_at": "2023-01-01T00:00:00Z",
            },
            {
                "event_id": "srcA:123",
                "revision": 1,
                "is_active_revision": False,
                "revision_reason": REVISION_REASON_CORRECTED,
                "source_native_event_id": "123",
                "bond_code": "110001",
                "announcement_date": "2023-01-01",
                "delisting_date": "2023-01-15",
                "source": "srcA",
                "updated_at": "2023-01-02T00:00:00Z",
            },
        ]
    )

    write_ledger(original_df, str(ledger_path))
    loaded = read_ledger(str(ledger_path))

    assert loaded["revision_reason"].tolist() == [
        REVISION_REASON_ACTIVE,
        REVISION_REASON_CORRECTED,
    ]
    assert loaded["revision"].tolist() == [0, 1]
    assert loaded["is_active_revision"].tolist() == [True, False]


def test_date_validation_rejection():
    ingress_df = pd.DataFrame(
        [
            _ingress_row("1"),
            _ingress_row("2", bond_code="110002", announcement_date=""),
            _ingress_row("3", bond_code="110003", delisting_date=""),
            _ingress_row(
                "4",
                bond_code="110004",
                announcement_date="2023-01-10",
                delisting_date="2023-01-01",
            ),
        ]
    )
    ledger_df = pd.DataFrame(columns=LEDGER_COLUMNS)

    new_ledger, rejected = process_ingress_to_ledger(ingress_df, ledger_df)

    assert len(new_ledger) == 1
    assert new_ledger.iloc[0]["event_id"] == "srcA:1"

    assert len(rejected) == 3
    reasons = {r["reason"] for r in rejected}
    assert reasons == {
        "MISSING_ANNOUNCEMENT_DATE",
        "MISSING_DELISTING_DATE",
        "INVALID_DATE_ORDER",
    }
