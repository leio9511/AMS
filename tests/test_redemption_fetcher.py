import json
from unittest.mock import patch

import pandas as pd
import pytest

from etl.redemption_fetcher import (
    BOOTSTRAP_START_DATE,
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


def test_fetch_and_build_import_csv_returns_empty_abort_and_refreshes_rejected_trace_when_all_rows_are_rejected_as_duplicates(tmp_path):
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
        success=False,
        status="EMPTY_ABORT",
        row_count=0,
        rejected_count=2,
    )
    assert fetcher.filtered_snapshot_ids == ["118033SH_20260514", "118033SH_20260514"]

    written_import_df = pd.read_csv(import_csv_path, dtype=str, keep_default_na=False)
    assert written_import_df["source_native_event_id"].tolist() == ["OLD_EVENT"]

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
