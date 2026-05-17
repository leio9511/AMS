import json

import pandas as pd
import pytest

from etl.cb_provider_base import (
    DataProviderAuthError,
    DataProviderNetworkUnavailableError,
    DataProviderQuotaError,
    DataProviderRuntimeBugError,
)
from etl.redemption_fetcher import BOOTSTRAP_START_DATE, RedemptionFetcher
from etl.redemption_ledger import IMPORT_COLUMNS
from etl.tushare_provider import MappedRedemptionResult


class StubProvider:
    def __init__(self, result=None, error=None, trade_calendar_result=None):
        self.result = result
        self.error = error
        self.trade_calendar_result = trade_calendar_result or []
        self.calls = []
        self.trade_calendar_calls = []

    def fetch_and_map_redemption_events(self, start_date, end_date):
        self.calls.append((start_date, end_date))
        if self.error is not None:
            raise self.error
        return self.result

    def fetch_trade_calendar(self, start_date, end_date):
        self.trade_calendar_calls.append((start_date, end_date))
        return list(self.trade_calendar_result)


def _mapped_result(rows):
    return MappedRedemptionResult(
        df=pd.DataFrame(rows, columns=IMPORT_COLUMNS),
        filtered_snapshot_ids=[row["source_native_event_id"] for row in rows],
        rejected_duplicates=[],
    )


def _manual_command_row(
    command="DECLARE",
    bond_code="123456.SH",
    announcement_date="2026-05-17",
    delisting_date="2026-06-20",
    reason="manual degraded fact",
    created_at="2026-05-17T10:00:00Z",
):
    return {
        "command": command,
        "source_native_event_id": f"{bond_code}_{announcement_date}",
        "bond_code": bond_code,
        "announcement_date": announcement_date,
        "delisting_date": delisting_date,
        "reason": reason,
        "created_at": created_at,
    }


def _write_manual_events(path, rows, columns=None):
    columns = columns or [
        "command",
        "source_native_event_id",
        "bond_code",
        "announcement_date",
        "delisting_date",
        "reason",
        "created_at",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _write_baseline(tmp_path):
    state_path = tmp_path / "data" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "last_successful_sync": "2026-05-16T00:00:00Z",
                "version": "1.0",
                "previous_id_set": ["BASELINE"],
            }
        ),
        encoding="utf-8",
    )
    return state_path


def _fetcher(tmp_path, provider, baseline=True):
    state_path = _write_baseline(tmp_path) if baseline else tmp_path / "data" / "state.json"
    return RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "data" / "import.csv"),
        ledger_csv_path=str(tmp_path / "data" / "ledger.csv"),
        canonical_csv_path=str(tmp_path / "data" / "canonical.csv"),
        trace_json_path=str(tmp_path / "data" / "trace.json"),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(state_path),
        freshness_report_path=str(tmp_path / "data" / "freshness.json"),
        manual_events_path=str(tmp_path / "data" / "manual_events.csv"),
        manual_review_completions_path=str(tmp_path / "data" / "manual_review_completions.json"),
        manual_degraded_ledger_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_ledger.csv"),
        manual_degraded_canonical_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_canonical.csv"),
        manual_degraded_trace_json_path=str(tmp_path / "data" / "reports" / "manual_degraded_trace.json"),
        today_fn=lambda: "2026-05-17",
    )


def _freshness_status(fetcher):
    with open(fetcher.freshness_report_path, "r", encoding="utf-8") as handle:
        return json.load(handle)["pipeline_status"]


def test_normal_tushare_success_ignores_manual_command_log(tmp_path):
    provider = StubProvider(
        result=_mapped_result(
            [
                {
                    "source_native_event_id": "TUSHARE_20260517",
                    "bond_code": "118033",
                    "announcement_date": "2026-05-17",
                    "delisting_date": "2026-06-20",
                    "source": "tushare",
                    "updated_at": "2026-05-17T00:00:00Z",
                }
            ]
        ),
        trade_calendar_result=["2026-05-17"],
    )
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row(bond_code="999999.SH")])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "OK"
    written = pd.read_csv(fetcher.import_csv_path, dtype=str, keep_default_na=False)
    assert written["source"].tolist() == ["tushare"]
    assert written["source_native_event_id"].tolist() == ["TUSHARE_20260517"]
    assert _freshness_status(fetcher) == "NORMAL"


def test_network_failure_with_baseline_and_manual_facts_enters_manual_degraded(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "MANUAL_DEGRADED"
    assert result.ingress_count == 1
    written = pd.read_csv(fetcher.import_csv_path, dtype=str, keep_default_na=False)
    assert list(written.columns) == IMPORT_COLUMNS
    assert written["source"].tolist() == ["manual"]
    degraded_ledger = pd.read_csv(fetcher.manual_degraded_ledger_csv_path, dtype=str, keep_default_na=False)
    degraded_canonical = pd.read_csv(fetcher.manual_degraded_canonical_csv_path, dtype=str, keep_default_na=False)
    with open(fetcher.manual_degraded_trace_json_path, "r", encoding="utf-8") as handle:
        degraded_trace = json.load(handle)
    assert degraded_ledger["source"].tolist() == ["manual"]
    assert degraded_canonical["bond_code"].tolist() == ["123456.SH"]
    assert degraded_trace["ingress_artifact_path"] == fetcher.import_csv_path
    assert result.ledger_event_count == 1
    assert result.canonical_date_count == 1
    assert _freshness_status(fetcher) == "MANUAL_DEGRADED"


def test_network_failure_without_baseline_returns_bootstrap_required(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider, baseline=False)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "BOOTSTRAP_REQUIRED"
    assert not (tmp_path / "data" / "import.csv").exists()
    assert _freshness_status(fetcher) == "BOOTSTRAP_REQUIRED"


def test_network_failure_with_baseline_empty_manual_and_no_completion_returns_freshness_empty(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "FRESHNESS_EMPTY"
    assert _freshness_status(fetcher) == "FRESHNESS_EMPTY"


def test_network_failure_with_baseline_empty_manual_and_completion_returns_manual_no_events(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "manual_review_completions.json").write_text(
        json.dumps([{"announcement_date": "2026-05-17", "reason": "done"}]),
        encoding="utf-8",
    )

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "MANUAL_NO_EVENTS"
    assert result.ingress_count == 0
    assert not (tmp_path / "data" / "import.csv").exists()
    assert _freshness_status(fetcher) == "MANUAL_NO_EVENTS"


def _assert_failure_does_not_use_manual_fallback(tmp_path, error, status):
    provider = StubProvider(error=error)
    fetcher = _fetcher(tmp_path, provider)
    manual_events_path = tmp_path / "data" / "manual_events.csv"
    _write_manual_events(manual_events_path, [_manual_command_row()])
    manual_events_path.chmod(0o000)
    try:
        result = fetcher.run_redemption_sync_pipeline()
    finally:
        manual_events_path.chmod(0o644)

    assert result.success is False
    assert result.status == status
    assert not (tmp_path / "data" / "import.csv").exists()
    assert _freshness_status(fetcher) == status


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (DataProviderAuthError("bad token"), "AUTH_FAILED"),
        (DataProviderQuotaError("quota"), "QUOTA_EXCEEDED"),
        (DataProviderRuntimeBugError("bug"), "RUNTIME_BUG"),
    ],
)
def test_non_network_failures_never_read_or_use_manual_fallback(tmp_path, error, status):
    _assert_failure_does_not_use_manual_fallback(tmp_path, error, status)


def test_auth_failure_never_reads_or_uses_manual_fallback(tmp_path):
    _assert_failure_does_not_use_manual_fallback(
        tmp_path,
        DataProviderAuthError("bad token"),
        "AUTH_FAILED",
    )


def test_quota_failure_never_reads_or_uses_manual_fallback(tmp_path):
    _assert_failure_does_not_use_manual_fallback(
        tmp_path,
        DataProviderQuotaError("quota"),
        "QUOTA_EXCEEDED",
    )


def test_runtime_bug_never_reads_or_uses_manual_fallback(tmp_path):
    _assert_failure_does_not_use_manual_fallback(
        tmp_path,
        DataProviderRuntimeBugError("bug"),
        "RUNTIME_BUG",
    )


def test_plain_provider_exception_maps_to_runtime_bug_and_never_uses_manual_fallback(tmp_path):
    provider = StubProvider(error=RuntimeError("plain mapping explosion"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "RUNTIME_BUG"
    assert not (tmp_path / "data" / "import.csv").exists()
    assert not (tmp_path / "data" / "reports" / "manual_degraded_trace.json").exists()
    assert _freshness_status(fetcher) == "RUNTIME_BUG"


def test_degraded_facts_are_filtered_to_target_announcement_date(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(
        tmp_path / "data" / "manual_events.csv",
        [_manual_command_row(announcement_date="2026-05-16")],
    )

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "FRESHNESS_EMPTY"
    assert not (tmp_path / "data" / "import.csv").exists()


def test_degraded_run_discards_prior_manual_degraded_state_for_current_target_date(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    old_ledger_path = tmp_path / "data" / "reports" / "manual_degraded_ledger.csv"
    old_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    old_ledger_path.write_text(
        "event_id,revision,is_active_revision,revision_reason,source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
        "manual:OLD_2026-05-16,0,True,ACTIVE,OLD_2026-05-16,OLD,2026-05-16,2026-06-16,manual,2026-05-16T00:00:00Z\n",
        encoding="utf-8",
    )
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row(bond_code="CURRENT")])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.status == "MANUAL_DEGRADED"
    degraded_ledger = pd.read_csv(fetcher.manual_degraded_ledger_csv_path, dtype=str, keep_default_na=False)
    assert degraded_ledger["bond_code"].tolist() == ["CURRENT"]
    assert degraded_ledger["announcement_date"].tolist() == ["2026-05-17"]


def test_manual_degraded_wave3_failure_writes_freshness_report(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    def fail_wave3(**kwargs):
        raise RuntimeError("degraded wave3 failed")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("etl.redemption_fetcher.run_redemption_wave3_pipeline", fail_wave3)
        result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "WAVE3_FAILED"
    assert _freshness_status(fetcher) == "WAVE3_FAILED"
    assert not (tmp_path / "data" / "import.csv").exists()


def test_manual_fallback_ingress_schema_asserts_redemption_ledger_import_columns(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(
        tmp_path / "data" / "manual_events.csv",
        [_manual_command_row()],
        columns=["command", "source_native_event_id", "bond_code", "announcement_date", "reason", "created_at"],
    )

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "RUNTIME_BUG"
    assert _freshness_status(fetcher) == "RUNTIME_BUG"
    assert not (tmp_path / "data" / "import.csv").exists()

    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])
    result = fetcher.run_redemption_sync_pipeline()
    assert result.status == "MANUAL_DEGRADED"
    written = pd.read_csv(fetcher.import_csv_path, dtype=str, keep_default_na=False)
    assert list(written.columns) == IMPORT_COLUMNS
