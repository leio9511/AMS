import json
from unittest.mock import patch

import pandas as pd
import pytest

from etl.redemption_fetcher import (
    BOOTSTRAP_START_DATE,
    EMPTY_SNAPSHOT_WARNING_MESSAGE,
    EMPTY_SNAPSHOT_WARNING_SUGGESTED_ACTION,
    FetchResult,
    PipelineResult,
    RedemptionFetcher,
    STATE_TRACKER_VERSION,
)
from etl.tushare_provider import IMPORT_COLUMNS, MappedRedemptionResult


class StubProvider:
    def __init__(self, result=None, error=None, trade_calendar_result=None):
        self.result = result
        self.error = error
        self.trade_calendar_result = trade_calendar_result or []
        self.calls = []
        self.trade_calendar_calls = []
        self.events = []

    def fetch_and_map_redemption_events(self, start_date, end_date):
        self.calls.append((start_date, end_date))
        self.events.append(("fetch", start_date, end_date))
        if self.error is not None:
            raise self.error
        return self.result

    def fetch_trade_calendar(self, start_date, end_date):
        self.trade_calendar_calls.append((start_date, end_date))
        self.events.append(("trade_calendar", start_date, end_date))
        return list(self.trade_calendar_result)


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


def test_fetch_and_build_import_csv_preserves_existing_import_and_rejected_trace_when_all_rows_are_rejected_as_duplicates(tmp_path):
    import_csv_path = tmp_path / "artifacts" / "import.csv"
    rejected_trace_path = tmp_path / "artifacts" / "rejected.json"

    import_csv_path.parent.mkdir(parents=True, exist_ok=True)
    import_csv_path.write_text(
        "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
        "OLD_EVENT,110001,2026-05-01,2026-05-10,tushare,2026-05-01T00:00:00Z\n",
        encoding="utf-8",
    )
    rejected_trace_path.write_text('[{"stale": true}]', encoding="utf-8")

    duplicate_payload = [
        {"ts_code": "118033.SH", "ann_date": "20260514", "call_type": "强赎", "row": "alpha"},
        {"ts_code": "118033.SH", "ann_date": "20260514", "call_type": "强赎", "row": "beta"},
    ]
    provider = StubProvider(
        result=_mapped_result(
            df_rows=[],
            filtered_snapshot_ids=["118033SH_20260514", "118033SH_20260514"],
            rejected_duplicates=duplicate_payload,
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        rejected_trace_path=str(rejected_trace_path),
        today_fn=lambda: "2026-05-15",
    )

    result = fetcher.fetch_and_build_import_csv()

    assert result == FetchResult(
        success=True,
        status="OK",
        row_count=0,
        rejected_count=2,
    )
    assert fetcher.filtered_snapshot_ids == ["118033SH_20260514", "118033SH_20260514"]

    written_import_df = pd.read_csv(import_csv_path, dtype=str, keep_default_na=False)
    assert written_import_df.empty
    assert list(written_import_df.columns) == IMPORT_COLUMNS

    with open(rejected_trace_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == duplicate_payload



def test_fetch_and_build_import_csv_returns_empty_abort_without_creating_a_misleading_success_import_artifact_for_true_empty_snapshot(tmp_path):
    import_csv_path = tmp_path / "artifacts" / "import.csv"
    rejected_trace_path = tmp_path / "artifacts" / "rejected.json"

    provider = StubProvider(
        result=_mapped_result(
            df_rows=[],
            filtered_snapshot_ids=[],
            rejected_duplicates=[],
        )
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        rejected_trace_path=str(rejected_trace_path),
        today_fn=lambda: "2026-05-15",
    )

    result = fetcher.fetch_and_build_import_csv()

    assert result == FetchResult(
        success=False,
        status="EMPTY_ABORT",
        row_count=0,
        rejected_count=0,
    )
    assert fetcher.filtered_snapshot_ids == []
    assert not import_csv_path.exists()
    assert not rejected_trace_path.exists()



def test_fetch_and_build_import_csv_returns_api_failed_without_mutating_existing_fetch_outputs_or_observation_baseline(tmp_path):
    import_csv_path = tmp_path / "artifacts" / "import.csv"
    rejected_trace_path = tmp_path / "artifacts" / "rejected.json"

    import_csv_path.parent.mkdir(parents=True, exist_ok=True)
    import_csv_path.write_text(
        "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
        "OLD_EVENT,110001,2026-05-01,2026-05-10,tushare,2026-05-01T00:00:00Z\n",
        encoding="utf-8",
    )
    rejected_trace_path.write_text('[{"stale": true}]', encoding="utf-8")

    provider = StubProvider(error=RuntimeError("provider exploded"))
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        rejected_trace_path=str(rejected_trace_path),
        today_fn=lambda: "2026-05-15",
    )
    fetcher.filtered_snapshot_ids = ["PREVIOUS_BASELINE"]

    result = fetcher.fetch_and_build_import_csv()

    assert result == FetchResult(
        success=False,
        status="API_FAILED",
        row_count=0,
        rejected_count=0,
    )
    assert fetcher.filtered_snapshot_ids == ["PREVIOUS_BASELINE"]

    written_import_df = pd.read_csv(import_csv_path, dtype=str, keep_default_na=False)
    assert written_import_df["source_native_event_id"].tolist() == ["OLD_EVENT"]

    with open(rejected_trace_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == [{"stale": True}]


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


def test_run_redemption_sync_pipeline_writes_empty_snapshot_warning_and_preserves_tracker_baseline_on_empty_abort(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    rejected_trace_path = tmp_path / "data" / "rejected.json"
    state_path = tmp_path / "data" / "state.json"
    freshness_report_path = tmp_path / "data" / "freshness.json"

    for path, content in [
        (
            import_csv_path,
            "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
            "OLD_EVENT,110001,2026-05-01,2026-05-10,tushare,2026-05-01T00:00:00Z\n",
        ),
        (ledger_csv_path, "event_id\nOLD_LEDGER_EVENT\n"),
        (canonical_csv_path, "date\n2026-05-14\n"),
        (trace_json_path, json.dumps({"trace": "keep"})),
        (rejected_trace_path, json.dumps([{"rejected": "keep"}])),
        (
            state_path,
            json.dumps(
                {
                    "last_successful_sync": "2026-05-14T00:00:00Z",
                    "version": STATE_TRACKER_VERSION,
                    "previous_id_set": ["118033SH_20260514", "127001SZ_20260515"],
                }
            ),
        ),
        (
            freshness_report_path,
            json.dumps(
                {
                    "generated_at": "2026-05-14T00:00:00Z",
                    "pipeline_status": "NORMAL",
                    "empty_snapshot_warning": None,
                    "disappearance_warning": {"missing_ids": ["OLD"]},
                }
            ),
        ),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    provider = StubProvider(
        result=_mapped_result(
            df_rows=[],
            filtered_snapshot_ids=[],
            rejected_duplicates=[],
        ),
        trade_calendar_result=["2026-05-14", "2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(rejected_trace_path),
        state_path=str(state_path),
        freshness_report_path=str(freshness_report_path),
        today_fn=lambda: "2026-05-15",
    )

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline") as wave3_mock:
        result = fetcher.run_redemption_sync_pipeline()

    assert result == PipelineResult(
        success=False,
        status="EMPTY_ABORT",
        ingress_count=0,
        ledger_event_count=0,
        canonical_date_count=0,
        disappearance_warning=None,
    )
    assert provider.calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]
    assert provider.trade_calendar_calls == []
    wave3_mock.assert_not_called()

    with open(freshness_report_path, "r", encoding="utf-8") as handle:
        freshness_payload = json.load(handle)
    assert freshness_payload["pipeline_status"] == "EMPTY_ABORT"
    assert freshness_payload["empty_snapshot_warning"] == {
        "message": EMPTY_SNAPSHOT_WARNING_MESSAGE,
        "suggested_action": EMPTY_SNAPSHOT_WARNING_SUGGESTED_ACTION,
    }
    assert freshness_payload["disappearance_warning"] is None

    with open(state_path, "r", encoding="utf-8") as handle:
        tracker_payload = json.load(handle)
    assert tracker_payload == {
        "last_successful_sync": "2026-05-14T00:00:00Z",
        "version": STATE_TRACKER_VERSION,
        "previous_id_set": ["118033SH_20260514", "127001SZ_20260515"],
    }

    written_import_df = pd.read_csv(import_csv_path, dtype=str, keep_default_na=False)
    assert written_import_df["source_native_event_id"].tolist() == ["OLD_EVENT"]
    written_ledger_df = pd.read_csv(ledger_csv_path, dtype=str, keep_default_na=False)
    assert written_ledger_df["event_id"].tolist() == ["OLD_LEDGER_EVENT"]
    written_canonical_df = pd.read_csv(canonical_csv_path, dtype=str, keep_default_na=False)
    assert written_canonical_df["date"].tolist() == ["2026-05-14"]
    with open(trace_json_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == {"trace": "keep"}
    with open(rejected_trace_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == [{"rejected": "keep"}]



def test_run_redemption_sync_pipeline_returns_fetch_failed_without_invoking_trade_calendar_or_wave3(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    rejected_trace_path = tmp_path / "data" / "rejected.json"
    state_path = tmp_path / "data" / "state.json"
    freshness_report_path = tmp_path / "data" / "freshness.json"

    provider = StubProvider(error=RuntimeError("provider exploded"), trade_calendar_result=["2026-05-14"])
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(rejected_trace_path),
        state_path=str(state_path),
        freshness_report_path=str(freshness_report_path),
        today_fn=lambda: "2026-05-15",
    )

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline") as wave3_mock:
        result = fetcher.run_redemption_sync_pipeline()

    assert result == PipelineResult(
        success=False,
        status="FETCH_FAILED",
        ingress_count=0,
        ledger_event_count=0,
        canonical_date_count=0,
        disappearance_warning=None,
    )
    assert provider.calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]
    assert provider.trade_calendar_calls == []
    wave3_mock.assert_not_called()



def test_run_redemption_sync_pipeline_leaves_existing_outputs_unchanged_on_fetch_failed(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    rejected_trace_path = tmp_path / "data" / "rejected.json"
    state_path = tmp_path / "data" / "state.json"
    freshness_report_path = tmp_path / "data" / "freshness.json"

    initial_artifacts = {
        import_csv_path: (
            "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
            "OLD_EVENT,110001,2026-05-01,2026-05-10,tushare,2026-05-01T00:00:00Z\n"
        ),
        ledger_csv_path: "event_id\nOLD_LEDGER_EVENT\n",
        canonical_csv_path: "date\n2026-05-14\n",
        trace_json_path: json.dumps({"trace": "keep"}),
        rejected_trace_path: json.dumps([{"rejected": "keep"}]),
        state_path: json.dumps(
            {
                "last_successful_sync": "2026-05-14T00:00:00Z",
                "version": STATE_TRACKER_VERSION,
                "previous_id_set": ["118033SH_20260514", "127001SZ_20260515"],
            }
        ),
        freshness_report_path: json.dumps(
            {
                "generated_at": "2026-05-14T00:00:00Z",
                "pipeline_status": "NORMAL",
                "empty_snapshot_warning": None,
                "disappearance_warning": {"missing_ids": ["OLD"]},
            }
        ),
    }

    expected_bytes = {}
    for path, content in initial_artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        expected_bytes[path] = path.read_bytes()

    provider = StubProvider(error=RuntimeError("provider exploded"))
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(rejected_trace_path),
        state_path=str(state_path),
        freshness_report_path=str(freshness_report_path),
        today_fn=lambda: "2026-05-15",
    )

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline") as wave3_mock:
        result = fetcher.run_redemption_sync_pipeline()

    assert result == PipelineResult(
        success=False,
        status="FETCH_FAILED",
        ingress_count=0,
        ledger_event_count=0,
        canonical_date_count=0,
        disappearance_warning=None,
    )
    assert provider.trade_calendar_calls == []
    wave3_mock.assert_not_called()

    for path, original_bytes in expected_bytes.items():
        assert path.read_bytes() == original_bytes



def test_run_redemption_sync_pipeline_updates_tracker_and_writes_normal_freshness_report_after_successful_non_empty_run(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    rejected_trace_path = tmp_path / "data" / "rejected.json"
    state_path = tmp_path / "data" / "state.json"
    freshness_report_path = tmp_path / "data" / "freshness.json"

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
            filtered_snapshot_ids=["127001SZ_20260515", "118033SH_20260514"],
            rejected_duplicates=[],
        ),
        trade_calendar_result=["2026-05-14", "2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(rejected_trace_path),
        state_path=str(state_path),
        freshness_report_path=str(freshness_report_path),
        today_fn=lambda: "2026-05-15",
    )

    def fake_wave3(**kwargs):
        pd.DataFrame(
            [
                {"event_id": "tushare:118033SH_20260514"},
                {"event_id": "tushare:127001SZ_20260515"},
                {"event_id": "tushare:EXTRA_20260515"},
            ]
        ).to_csv(ledger_csv_path, index=False)
        pd.DataFrame(
            [
                {"date": "2026-05-14"},
                {"date": "2026-05-15"},
            ]
        ).to_csv(canonical_csv_path, index=False)
        trace_json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "OK"
    assert result.ingress_count == 2
    assert result.ledger_event_count == 3
    assert result.canonical_date_count == 2
    assert result.disappearance_warning is None
    assert provider.calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]
    assert provider.trade_calendar_calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]

    with open(freshness_report_path, "r", encoding="utf-8") as handle:
        freshness_payload = json.load(handle)
    assert freshness_payload["pipeline_status"] == "NORMAL"
    assert freshness_payload["empty_snapshot_warning"] is None
    assert freshness_payload["disappearance_warning"] is None
    assert freshness_payload["generated_at"].endswith("Z")

    with open(state_path, "r", encoding="utf-8") as handle:
        tracker_payload = json.load(handle)
    assert tracker_payload["version"] == STATE_TRACKER_VERSION
    assert tracker_payload["previous_id_set"] == ["118033SH_20260514", "127001SZ_20260515"]
    assert tracker_payload["last_successful_sync"].endswith("Z")


def test_run_redemption_sync_pipeline_writes_disappearance_warning_from_previous_id_set_diff(tmp_path):
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    state_path = tmp_path / "data" / "state.json"
    freshness_report_path = tmp_path / "data" / "freshness.json"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "last_successful_sync": "2026-05-14T00:00:00Z",
                "version": "0.9",
                "previous_id_set": [
                    "118033SH_20260514",
                    "127001SZ_20260515",
                    "110001SH_20260516",
                ],
            }
        ),
        encoding="utf-8",
    )

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
            filtered_snapshot_ids=["127001SZ_20260515", "118033SH_20260514"],
            rejected_duplicates=[],
        ),
        trade_calendar_result=["2026-05-14", "2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "data" / "import.csv"),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(state_path),
        freshness_report_path=str(freshness_report_path),
        today_fn=lambda: "2026-05-15",
    )

    def fake_wave3(**kwargs):
        pd.DataFrame([{"event_id": "tushare:118033SH_20260514"}]).to_csv(ledger_csv_path, index=False)
        pd.DataFrame([{"date": "2026-05-15"}]).to_csv(canonical_csv_path, index=False)
        trace_json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    expected_warning = {
        "missing_ids": ["110001SH_20260516"],
        "previous_count": 3,
        "current_count": 2,
    }
    assert result.disappearance_warning == expected_warning

    with open(freshness_report_path, "r", encoding="utf-8") as handle:
        freshness_payload = json.load(handle)
    assert freshness_payload["pipeline_status"] == "NORMAL"
    assert freshness_payload["disappearance_warning"] == expected_warning


def test_run_redemption_sync_pipeline_calls_trade_calendar_and_wave3_only_after_ok_fetch_result(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"

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
        ),
        trade_calendar_result=["2026-05-14", "2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(tmp_path / "data" / "state.json"),
        freshness_report_path=str(tmp_path / "data" / "freshness.json"),
        today_fn=lambda: "2026-05-15",
    )

    wave3_calls = []

    def fake_wave3(**kwargs):
        provider.events.append(("wave3", kwargs["target_dates"]))
        wave3_calls.append(kwargs)
        pd.DataFrame([{"event_id": "tushare:118033SH_20260514"}]).to_csv(ledger_csv_path, index=False)
        pd.DataFrame([{"date": "2026-05-15"}]).to_csv(canonical_csv_path, index=False)
        trace_json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    assert result == PipelineResult(
        success=True,
        status="OK",
        ingress_count=1,
        ledger_event_count=1,
        canonical_date_count=1,
        disappearance_warning=None,
    )
    assert provider.events == [
        ("fetch", BOOTSTRAP_START_DATE, "2026-05-15"),
        ("trade_calendar", BOOTSTRAP_START_DATE, "2026-05-15"),
        ("wave3", ["2026-05-14", "2026-05-15"]),
    ]
    assert len(wave3_calls) == 1
    assert wave3_calls[0] == {
        "import_csv_path": str(import_csv_path),
        "ledger_csv_path": str(ledger_csv_path),
        "canonical_csv_path": str(canonical_csv_path),
        "trace_json_path": str(trace_json_path),
        "target_dates": ["2026-05-14", "2026-05-15"],
    }


def test_run_redemption_sync_pipeline_uses_one_run_scoped_today_value_for_fetch_and_trade_calendar(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"

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
        ),
        trade_calendar_result=["2026-05-15"],
    )

    today_values = iter(["2026-05-15", "2026-05-16"])
    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(tmp_path / "data" / "state.json"),
        freshness_report_path=str(tmp_path / "data" / "freshness.json"),
        today_fn=lambda: next(today_values),
    )

    def fake_wave3(**kwargs):
        pd.DataFrame([{"event_id": "tushare:118033SH_20260514"}]).to_csv(ledger_csv_path, index=False)
        pd.DataFrame([{"date": "2026-05-15"}]).to_csv(canonical_csv_path, index=False)
        trace_json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert provider.calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]
    assert provider.trade_calendar_calls == [(BOOTSTRAP_START_DATE, "2026-05-15")]


def test_run_redemption_sync_pipeline_cleans_backup_sidecars_after_successful_wave3_commit(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"

    original_ledger = "event_id\nOLD_LEDGER_EVENT\n"
    original_canonical = "date\n2026-05-14\n"
    original_trace = json.dumps({"trace": "before"})

    for path, content in [
        (ledger_csv_path, original_ledger),
        (canonical_csv_path, original_canonical),
        (trace_json_path, original_trace),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

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
        ),
        trade_calendar_result=["2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(tmp_path / "data" / "state.json"),
        freshness_report_path=str(tmp_path / "data" / "freshness.json"),
        today_fn=lambda: "2026-05-15",
    )

    def fake_wave3(**kwargs):
        backup_paths = {
            ledger_csv_path: ledger_csv_path.parent / f"{ledger_csv_path.name}.bak",
            canonical_csv_path: canonical_csv_path.parent / f"{canonical_csv_path.name}.bak",
            trace_json_path: trace_json_path.parent / f"{trace_json_path.name}.bak",
        }
        assert backup_paths[ledger_csv_path].read_text(encoding="utf-8") == original_ledger
        assert backup_paths[canonical_csv_path].read_text(encoding="utf-8") == original_canonical
        assert backup_paths[trace_json_path].read_text(encoding="utf-8") == original_trace

        ledger_csv_path.write_text("event_id\nNEW_LEDGER_EVENT\n", encoding="utf-8")
        canonical_csv_path.write_text("date\n2026-05-15\n", encoding="utf-8")
        trace_json_path.write_text(json.dumps({"trace": "after"}), encoding="utf-8")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    assert result.status == "OK"
    assert not (ledger_csv_path.parent / f"{ledger_csv_path.name}.bak").exists()
    assert not (canonical_csv_path.parent / f"{canonical_csv_path.name}.bak").exists()
    assert not (trace_json_path.parent / f"{trace_json_path.name}.bak").exists()
    assert ledger_csv_path.read_text(encoding="utf-8") == "event_id\nNEW_LEDGER_EVENT\n"
    assert canonical_csv_path.read_text(encoding="utf-8") == "date\n2026-05-15\n"
    assert json.loads(trace_json_path.read_text(encoding="utf-8")) == {"trace": "after"}


def test_run_redemption_sync_pipeline_rolls_back_truth_source_files_and_deletes_temporary_fetch_outputs_on_wave3_failure(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    rejected_trace_path = tmp_path / "data" / "rejected.json"

    original_ledger = "event_id\nOLD_LEDGER_EVENT\n"
    original_trace = json.dumps({"trace": "before"})

    ledger_csv_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_csv_path.write_text(original_ledger, encoding="utf-8")
    trace_json_path.write_text(original_trace, encoding="utf-8")

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
            rejected_duplicates=[{"ts_code": "118033.SH", "ann_date": "20260514"}],
        ),
        trade_calendar_result=["2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(rejected_trace_path),
        state_path=str(tmp_path / "data" / "state.json"),
        freshness_report_path=str(tmp_path / "data" / "freshness.json"),
        today_fn=lambda: "2026-05-15",
    )

    def fake_wave3(**kwargs):
        ledger_csv_path.write_text("event_id\nPARTIAL_LEDGER_EVENT\n", encoding="utf-8")
        canonical_csv_path.write_text("date\n2026-05-15\n", encoding="utf-8")
        trace_json_path.write_text(json.dumps({"trace": "partial"}), encoding="utf-8")
        raise RuntimeError("wave3 exploded")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    assert result == PipelineResult(
        success=False,
        status="WAVE3_FAILED",
        ingress_count=1,
        ledger_event_count=0,
        canonical_date_count=0,
        disappearance_warning=None,
    )
    assert ledger_csv_path.read_text(encoding="utf-8") == original_ledger
    assert not canonical_csv_path.exists()
    assert trace_json_path.read_text(encoding="utf-8") == original_trace
    assert not import_csv_path.exists()
    assert not rejected_trace_path.exists()
    assert not (ledger_csv_path.parent / f"{ledger_csv_path.name}.bak").exists()
    assert not (canonical_csv_path.parent / f"{canonical_csv_path.name}.bak").exists()
    assert not (trace_json_path.parent / f"{trace_json_path.name}.bak").exists()


def test_run_redemption_sync_pipeline_does_not_advance_tracker_or_write_post_failure_freshness_report_on_wave3_failure(tmp_path):
    import_csv_path = tmp_path / "data" / "import.csv"
    ledger_csv_path = tmp_path / "data" / "ledger.csv"
    canonical_csv_path = tmp_path / "data" / "canonical.csv"
    trace_json_path = tmp_path / "data" / "trace.json"
    state_path = tmp_path / "data" / "state.json"
    freshness_report_path = tmp_path / "data" / "freshness.json"

    for path, content in [
        (ledger_csv_path, "event_id\nOLD_LEDGER_EVENT\n"),
        (canonical_csv_path, "date\n2026-05-14\n"),
        (trace_json_path, json.dumps({"trace": "before"})),
        (
            state_path,
            json.dumps(
                {
                    "last_successful_sync": "2026-05-14T00:00:00Z",
                    "version": STATE_TRACKER_VERSION,
                    "previous_id_set": ["OLD_BASELINE_EVENT"],
                }
            ),
        ),
        (
            freshness_report_path,
            json.dumps(
                {
                    "generated_at": "2026-05-14T00:00:00Z",
                    "pipeline_status": "NORMAL",
                    "empty_snapshot_warning": None,
                    "disappearance_warning": {"missing_ids": ["OLD_BASELINE_EVENT"]},
                }
            ),
        ),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    original_state_bytes = state_path.read_bytes()
    original_freshness_bytes = freshness_report_path.read_bytes()

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
        ),
        trade_calendar_result=["2026-05-15"],
    )

    fetcher = RedemptionFetcher(
        provider=provider,
        import_csv_path=str(import_csv_path),
        ledger_csv_path=str(ledger_csv_path),
        canonical_csv_path=str(canonical_csv_path),
        trace_json_path=str(trace_json_path),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(state_path),
        freshness_report_path=str(freshness_report_path),
        today_fn=lambda: "2026-05-15",
    )

    def fake_wave3(**kwargs):
        ledger_csv_path.write_text("event_id\nPARTIAL_LEDGER_EVENT\n", encoding="utf-8")
        canonical_csv_path.write_text("date\n2026-05-15\n", encoding="utf-8")
        trace_json_path.write_text(json.dumps({"trace": "partial"}), encoding="utf-8")
        raise RuntimeError("wave3 exploded")

    with patch("etl.redemption_fetcher.run_redemption_wave3_pipeline", side_effect=fake_wave3):
        result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "WAVE3_FAILED"
    assert state_path.read_bytes() == original_state_bytes
    assert freshness_report_path.read_bytes() == original_freshness_bytes
    with open(state_path, "r", encoding="utf-8") as handle:
        assert json.load(handle) == {
            "last_successful_sync": "2026-05-14T00:00:00Z",
            "version": STATE_TRACKER_VERSION,
            "previous_id_set": ["OLD_BASELINE_EVENT"],
        }
