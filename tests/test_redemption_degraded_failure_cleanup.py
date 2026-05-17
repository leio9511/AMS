import json

import pandas as pd
import pytest

from etl.cb_provider_base import DataProviderNetworkUnavailableError
from etl.redemption_fetcher import RedemptionFetcher
from etl.redemption_ledger import IMPORT_COLUMNS, LEDGER_COLUMNS


class StubProvider:
    def __init__(self, error=None):
        self.error = error

    def fetch_and_map_redemption_events(self, start_date, end_date):
        if self.error is not None:
            raise self.error
        raise AssertionError("unexpected normal fetch")

    def fetch_trade_calendar(self, start_date, end_date):
        return [end_date]


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


def _write_manual_events(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        rows,
        columns=[
            "command",
            "source_native_event_id",
            "bond_code",
            "announcement_date",
            "delisting_date",
            "reason",
            "created_at",
        ],
    ).to_csv(path, index=False)


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


def _fetcher(tmp_path, baseline=True):
    state_path = _write_baseline(tmp_path) if baseline else tmp_path / "data" / "state.json"
    return RedemptionFetcher(
        provider=StubProvider(error=DataProviderNetworkUnavailableError("network down")),
        import_csv_path=str(tmp_path / "data" / "import.csv"),
        ledger_csv_path=str(tmp_path / "data" / "ledger.csv"),
        canonical_csv_path=str(tmp_path / "data" / "canonical.csv"),
        trace_json_path=str(tmp_path / "data" / "trace.json"),
        rejected_trace_path=str(tmp_path / "data" / "rejected.json"),
        state_path=str(state_path),
        freshness_report_path=str(tmp_path / "data" / "freshness.json"),
        manual_events_path=str(tmp_path / "data" / "manual_events.csv"),
        manual_review_completions_path=str(tmp_path / "data" / "manual_review_completions.json"),
        manual_degraded_import_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_import.csv"),
        manual_degraded_effective_state_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_effective_state.csv"),
        manual_degraded_ledger_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_ledger.csv"),
        manual_degraded_canonical_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_canonical.csv"),
        manual_degraded_trace_json_path=str(tmp_path / "data" / "reports" / "manual_degraded_trace.json"),
        today_fn=lambda: "2026-05-17",
    )


def _write_stale_degraded_artifacts(fetcher):
    for path, content in [
        (fetcher.manual_degraded_import_csv_path, "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\nSTALE,STALE,2026-05-16,2026-06-16,manual,2026-05-16T00:00:00Z\n"),
        (fetcher.manual_degraded_effective_state_csv_path, "date,bond_code,redeem_risk,representative_event_id,representative_revision\n2026-05-17,STALE,True,manual:STALE,0\n"),
        (fetcher.manual_degraded_ledger_csv_path, "event_id,revision,is_active_revision,revision_reason,source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\nmanual:STALE,0,True,ACTIVE,STALE,STALE,2026-05-16,2026-06-16,manual,2026-05-16T00:00:00Z\n"),
        (fetcher.manual_degraded_canonical_csv_path, "date,bond_code,redeem_risk,representative_event_id,representative_revision\n2026-05-17,STALE,True,manual:STALE,0\n"),
        (fetcher.manual_degraded_trace_json_path, '{"pipeline_status":"MANUAL_DEGRADED"}'),
    ]:
        from pathlib import Path
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")


def _assert_no_degraded_artifacts(fetcher):
    assert not pd.io.common.file_exists(fetcher.manual_degraded_import_csv_path)
    assert not pd.io.common.file_exists(fetcher.manual_degraded_effective_state_csv_path)
    assert not pd.io.common.file_exists(fetcher.manual_degraded_ledger_csv_path)
    assert not pd.io.common.file_exists(fetcher.manual_degraded_canonical_csv_path)
    assert not pd.io.common.file_exists(fetcher.manual_degraded_trace_json_path)


def _freshness_payload(fetcher):
    with open(fetcher.freshness_report_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_freshness_empty_cleans_stale_degraded_operational_artifacts(tmp_path):
    fetcher = _fetcher(tmp_path)
    _write_stale_degraded_artifacts(fetcher)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "FRESHNESS_EMPTY"
    _assert_no_degraded_artifacts(fetcher)


def test_bootstrap_required_cleans_stale_degraded_operational_artifacts(tmp_path):
    fetcher = _fetcher(tmp_path, baseline=False)
    _write_stale_degraded_artifacts(fetcher)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "BOOTSTRAP_REQUIRED"
    _assert_no_degraded_artifacts(fetcher)


def test_manual_no_events_does_not_create_placeholder_business_or_truth_rows(tmp_path):
    fetcher = _fetcher(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "manual_review_completions.json").write_text(
        json.dumps([{"announcement_date": "2026-05-17", "reason": "review complete"}]),
        encoding="utf-8",
    )

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "MANUAL_NO_EVENTS"
    assert result.ingress_count == 0
    _assert_no_degraded_artifacts(fetcher)
    assert not (tmp_path / "data" / "import.csv").exists()
    assert not (tmp_path / "data" / "ledger.csv").exists()
    assert not (tmp_path / "data" / "canonical.csv").exists()
    assert not (tmp_path / "data" / "trace.json").exists()


def test_degraded_adapter_failure_cleans_partial_degraded_outputs(tmp_path):
    fetcher = _fetcher(tmp_path)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    def fail_after_partial_outputs(**kwargs):
        pd.DataFrame([_manual_command_row()], columns=IMPORT_COLUMNS).to_csv(
            kwargs["ledger_csv_path"], index=False
        )
        pd.DataFrame([{"date": "2026-05-17", "bond_code": "PARTIAL_EFFECTIVE"}]).to_csv(
            fetcher.manual_degraded_effective_state_csv_path, index=False
        )
        pd.DataFrame([{"date": "2026-05-17", "bond_code": "PARTIAL"}]).to_csv(
            kwargs["canonical_csv_path"], index=False
        )
        with open(kwargs["trace_json_path"], "w", encoding="utf-8") as handle:
            json.dump({"pipeline_status": "PARTIAL"}, handle)
        raise RuntimeError("adapter failed after partial outputs")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("etl.redemption_fetcher.run_redemption_wave3_pipeline", fail_after_partial_outputs)
        result = fetcher.run_redemption_sync_pipeline()

    assert result.success is False
    assert result.status == "WAVE3_FAILED"
    _assert_no_degraded_artifacts(fetcher)


def test_degraded_failure_statuses_are_not_normal_success(tmp_path):
    outcomes = []

    empty_fetcher = _fetcher(tmp_path / "empty")
    _write_manual_events(tmp_path / "empty" / "data" / "manual_events.csv", [])
    outcomes.append(empty_fetcher.run_redemption_sync_pipeline())
    outcomes.append(_freshness_payload(empty_fetcher))

    bootstrap_fetcher = _fetcher(tmp_path / "bootstrap", baseline=False)
    _write_manual_events(tmp_path / "bootstrap" / "data" / "manual_events.csv", [_manual_command_row()])
    outcomes.append(bootstrap_fetcher.run_redemption_sync_pipeline())
    outcomes.append(_freshness_payload(bootstrap_fetcher))

    no_events_fetcher = _fetcher(tmp_path / "no_events")
    (tmp_path / "no_events" / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "no_events" / "data" / "manual_review_completions.json").write_text(
        json.dumps([{"announcement_date": "2026-05-17"}]),
        encoding="utf-8",
    )
    outcomes.append(no_events_fetcher.run_redemption_sync_pipeline())
    outcomes.append(_freshness_payload(no_events_fetcher))

    statuses = [item.status if hasattr(item, "status") else item["pipeline_status"] for item in outcomes]
    assert statuses == [
        "FRESHNESS_EMPTY",
        "FRESHNESS_EMPTY",
        "BOOTSTRAP_REQUIRED",
        "BOOTSTRAP_REQUIRED",
        "MANUAL_NO_EVENTS",
        "MANUAL_NO_EVENTS",
    ]
    assert not ({"OK", "NORMAL"} & set(statuses))


def test_negative_path_cleanup_preserves_manual_audit_log_and_authoritative_truth(tmp_path):
    fetcher = _fetcher(tmp_path)
    manual_path = tmp_path / "data" / "manual_events.csv"
    _write_manual_events(manual_path, [])
    manual_before = manual_path.read_text(encoding="utf-8")

    ledger_path = tmp_path / "data" / "ledger.csv"
    canonical_path = tmp_path / "data" / "canonical.csv"
    trace_path = tmp_path / "data" / "trace.json"
    ledger_path.write_text(
        ",".join(LEDGER_COLUMNS) + "\ntushare:BASE,0,True,ACTIVE,BASE,110000.SH,2026-05-16,2026-06-16,tushare,2026-05-16T00:00:00Z\n",
        encoding="utf-8",
    )
    canonical_path.write_text(
        "date,bond_code,redeem_risk,representative_event_id,representative_revision\n2026-05-17,110000.SH,True,tushare:BASE,0\n",
        encoding="utf-8",
    )
    trace_path.write_text('{"pipeline_status":"NORMAL","sentinel":true}', encoding="utf-8")
    authoritative_before = {
        str(ledger_path): ledger_path.read_text(encoding="utf-8"),
        str(canonical_path): canonical_path.read_text(encoding="utf-8"),
        str(trace_path): trace_path.read_text(encoding="utf-8"),
    }
    _write_stale_degraded_artifacts(fetcher)

    result = fetcher.run_redemption_sync_pipeline()

    assert result.status == "FRESHNESS_EMPTY"
    assert manual_path.read_text(encoding="utf-8") == manual_before
    for path, content in authoritative_before.items():
        from pathlib import Path
        assert Path(path).read_text(encoding="utf-8") == content
    _assert_no_degraded_artifacts(fetcher)
