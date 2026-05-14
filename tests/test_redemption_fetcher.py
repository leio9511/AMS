import json
from unittest.mock import patch

import pandas as pd
import pytest

from etl.redemption_fetcher import (
    BOOTSTRAP_START_DATE,
    FetchResult,
    RedemptionFetcher,
)
from etl.tushare_provider import IMPORT_COLUMNS, MappedRedemptionResult


class StubProvider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def fetch_and_map_redemption_events(self, start_date, end_date):
        self.calls.append((start_date, end_date))
        if self.error is not None:
            raise self.error
        return self.result


def _mapped_result(df_rows, filtered_snapshot_ids, rejected_duplicates):
    return MappedRedemptionResult(
        df=pd.DataFrame(df_rows),
        filtered_snapshot_ids=filtered_snapshot_ids,
        rejected_duplicates=rejected_duplicates,
    )


def test_fetch_and_build_import_csv_writes_import_csv_and_current_rejected_trace_on_non_empty_ok_result(tmp_path):
    import_csv_path = tmp_path / "artifacts" / "import.csv"
    rejected_trace_path = tmp_path / "artifacts" / "rejected.json"

    rejected_trace_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_trace_path.write_text('{"stale": true}', encoding="utf-8")

    provider = StubProvider(
        result=_mapped_result(
            df_rows=[
                {
                    "source_native_event_id": "118033SH_20260514",
                    "bond_code": "118033",
                    "announcement_date": "2026-05-14",
                    "delisting_date": "2026-06-15",
                    "source": "tushare",
                    "updated_at": "2026-05-14T10:00:00Z",
                },
                {
                    "source_native_event_id": "127001SZ_20260515",
                    "bond_code": "127001",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "source": "tushare",
                    "updated_at": "2026-05-14T10:00:00Z",
                },
            ],
            filtered_snapshot_ids=[
                "118033SH_20260514",
                "127001SZ_20260515",
                "110001SH_20260516",
            ],
            rejected_duplicates=[
                {
                    "ts_code": "110001.SH",
                    "ann_date": "20260516",
                    "call_type": "强赎",
                    "call_date": "20260601",
                }
            ],
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        rejected_trace_path=str(rejected_trace_path),
        today_fn=lambda: "2026-05-15",
    )

    result = fetcher.fetch_and_build_import_csv()

    assert result == FetchResult(success=True, status="OK", row_count=2, rejected_count=1)
    assert provider.calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]

    written_import_df = pd.read_csv(import_csv_path, dtype=str, keep_default_na=False)
    assert written_import_df["source_native_event_id"].tolist() == [
        "118033SH_20260514",
        "127001SZ_20260515",
    ]

    with open(rejected_trace_path, "r", encoding="utf-8") as handle:
        rejected_payload = json.load(handle)
    assert rejected_payload == [
        {
            "ts_code": "110001.SH",
            "ann_date": "20260516",
            "call_type": "强赎",
            "call_date": "20260601",
        }
    ]


def test_fetch_and_build_import_csv_preserves_filtered_snapshot_ids_when_duplicates_are_rejected_but_other_rows_are_admitted(tmp_path):
    provider = StubProvider(
        result=_mapped_result(
            df_rows=[
                {
                    "source_native_event_id": "127001SZ_20260515",
                    "bond_code": "127001",
                    "announcement_date": "2026-05-15",
                    "delisting_date": "2026-06-20",
                    "source": "tushare",
                    "updated_at": "2026-05-14T10:00:00Z",
                }
            ],
            filtered_snapshot_ids=[
                "118033SH_20260514",
                "118033SH_20260514",
                "127001SZ_20260515",
            ],
            rejected_duplicates=[
                {"ts_code": "118033.SH", "ann_date": "20260514", "call_type": "强赎"},
                {"ts_code": "118033.SH", "ann_date": "20260514", "call_type": "强赎"},
            ],
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "import.csv"),
        rejected_trace_path=str(tmp_path / "rejected.json"),
        today_fn=lambda: "2026-05-15",
    )

    result = fetcher.fetch_and_build_import_csv()

    assert result.success is True
    assert result.status == "OK"
    assert result.row_count == 1
    assert result.rejected_count == 2
    assert fetcher.filtered_snapshot_ids == [
        "118033SH_20260514",
        "118033SH_20260514",
        "127001SZ_20260515",
    ]

    written_import_df = pd.read_csv(tmp_path / "import.csv", dtype=str, keep_default_na=False)
    assert written_import_df["source_native_event_id"].tolist() == ["127001SZ_20260515"]


def test_fetch_and_build_import_csv_supports_path_overrides_for_temp_artifact_writes(tmp_path):
    default_import_path = tmp_path / "default" / "import.csv"
    default_rejected_path = tmp_path / "default" / "rejected.json"
    override_import_path = tmp_path / "override" / "import.csv"
    override_rejected_path = tmp_path / "override" / "rejected.json"

    provider = StubProvider(
        result=_mapped_result(
            df_rows=[
                {
                    "source_native_event_id": "118033SH_20260514",
                    "bond_code": "118033",
                    "announcement_date": "2026-05-14",
                    "delisting_date": "2026-06-15",
                    "source": "tushare",
                    "updated_at": "2026-05-14T10:00:00Z",
                }
            ],
            filtered_snapshot_ids=["118033SH_20260514"],
            rejected_duplicates=[],
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(default_import_path),
        rejected_trace_path=str(override_rejected_path),
        today_fn=lambda: "2026-05-15",
    )

    result = fetcher.fetch_and_build_import_csv(import_csv_path=str(override_import_path))

    assert result == FetchResult(success=True, status="OK", row_count=1, rejected_count=0)
    assert override_import_path.exists()
    assert override_rejected_path.exists()
    assert not default_import_path.exists()
    assert not default_rejected_path.exists()

    with open(override_rejected_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == []


def test_fetch_and_build_import_csv_does_not_publish_new_import_csv_if_rejected_trace_publish_fails(tmp_path):
    import_csv_path = tmp_path / "artifacts" / "import.csv"
    rejected_trace_path = tmp_path / "artifacts" / "rejected.json"

    import_csv_path.parent.mkdir(parents=True, exist_ok=True)
    import_csv_path.write_text(
        "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
        "OLD_EVENT,110001,2026-05-01,2026-05-10,tushare,2026-05-01T00:00:00Z\n",
        encoding="utf-8",
    )
    rejected_trace_path.write_text('[{"stale": true}]', encoding="utf-8")

    provider = StubProvider(
        result=_mapped_result(
            df_rows=[
                {
                    "source_native_event_id": "NEW_EVENT",
                    "bond_code": "118033",
                    "announcement_date": "2026-05-14",
                    "delisting_date": "2026-06-15",
                    "source": "tushare",
                    "updated_at": "2026-05-14T10:00:00Z",
                }
            ],
            filtered_snapshot_ids=["NEW_EVENT"],
            rejected_duplicates=[{"ts_code": "110001.SH", "ann_date": "20260516"}],
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        rejected_trace_path=str(rejected_trace_path),
        today_fn=lambda: "2026-05-15",
    )

    original_replace = __import__("os").replace
    rejected_publish_attempts = {"count": 0}

    def fail_on_rejected_publish(src, dst):
        if dst == str(rejected_trace_path):
            rejected_publish_attempts["count"] += 1
            if rejected_publish_attempts["count"] == 1:
                raise OSError("simulated rejected trace publish failure")
        return original_replace(src, dst)

    with patch("etl.redemption_fetcher.os.replace", side_effect=fail_on_rejected_publish):
        with pytest.raises(OSError, match="simulated rejected trace publish failure"):
            fetcher.fetch_and_build_import_csv()

    written_import_df = pd.read_csv(import_csv_path, dtype=str, keep_default_na=False)
    assert written_import_df["source_native_event_id"].tolist() == ["OLD_EVENT"]

    with open(rejected_trace_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == [{"stale": True}]


def test_fetch_and_build_import_csv_raises_when_provider_result_is_empty_placeholder_scaffolding(tmp_path):
    provider = StubProvider(
        result=_mapped_result(
            df_rows=[],
            filtered_snapshot_ids=["118033SH_20260514"],
            rejected_duplicates=[],
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "import.csv"),
        rejected_trace_path=str(tmp_path / "rejected.json"),
        today_fn=lambda: "2026-05-15",
    )

    with pytest.raises(NotImplementedError, match="deferred to a later slice"):
        fetcher.fetch_and_build_import_csv()

    assert fetcher.filtered_snapshot_ids == ["118033SH_20260514"]
    assert not (tmp_path / "import.csv").exists()
    assert not (tmp_path / "rejected.json").exists()


def test_fetch_and_build_import_csv_raises_provider_errors_instead_of_normalizing_them(tmp_path):
    provider = StubProvider(error=RuntimeError("provider exploded"))
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "import.csv"),
        rejected_trace_path=str(tmp_path / "rejected.json"),
        today_fn=lambda: "2026-05-15",
    )

    with pytest.raises(RuntimeError, match="provider exploded"):
        fetcher.fetch_and_build_import_csv()

    assert provider.calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]
    assert not (tmp_path / "import.csv").exists()
    assert not (tmp_path / "rejected.json").exists()


def test_fetch_and_build_import_csv_raises_when_provider_omits_required_import_columns(tmp_path):
    incomplete_rows = [
        {
            "source_native_event_id": "118033SH_20260514",
            "bond_code": "118033",
            "announcement_date": "2026-05-14",
            "delisting_date": "2026-06-15",
            "source": "tushare",
        }
    ]
    provider = StubProvider(
        result=_mapped_result(
            df_rows=incomplete_rows,
            filtered_snapshot_ids=["118033SH_20260514"],
            rejected_duplicates=[],
        )
    )
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "import.csv"),
        rejected_trace_path=str(tmp_path / "rejected.json"),
        today_fn=lambda: "2026-05-15",
    )

    with pytest.raises(ValueError, match="missing required import columns: updated_at"):
        fetcher.fetch_and_build_import_csv()

    assert not (tmp_path / "import.csv").exists()
    assert not (tmp_path / "rejected.json").exists()


def test_fetch_and_build_import_csv_success_path_still_requires_all_import_columns(tmp_path):
    provider = StubProvider(
        result=_mapped_result(
            df_rows=[
                {
                    column: value
                    for column, value in {
                        "source_native_event_id": "118033SH_20260514",
                        "bond_code": "118033",
                        "announcement_date": "2026-05-14",
                        "delisting_date": "2026-06-15",
                        "source": "tushare",
                        "updated_at": "2026-05-14T10:00:00Z",
                    }.items()
                    if column in IMPORT_COLUMNS
                }
            ],
            filtered_snapshot_ids=["118033SH_20260514"],
            rejected_duplicates=[],
        )
    )
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "import.csv"),
        rejected_trace_path=str(tmp_path / "rejected.json"),
        today_fn=lambda: "2026-05-15",
    )

    result = fetcher.fetch_and_build_import_csv()

    assert result == FetchResult(success=True, status="OK", row_count=1, rejected_count=0)
