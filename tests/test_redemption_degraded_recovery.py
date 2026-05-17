import json
from pathlib import Path

import pandas as pd

from etl.cb_provider_base import DataProviderNetworkUnavailableError
from etl.redemption_fetcher import RedemptionFetcher
from etl.redemption_ledger import IMPORT_COLUMNS, LEDGER_COLUMNS, process_ingress_to_ledger
from etl.tushare_provider import MappedRedemptionResult


class StubProvider:
    def __init__(self, result=None, error=None, trade_calendar_result=None):
        self.result = result
        self.error = error
        self.trade_calendar_result = trade_calendar_result or ["2026-05-17"]
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


def _tushare_row(
    source_native_event_id="TUSHARE_20260517",
    bond_code="118033.SH",
    announcement_date="2026-05-17",
    delisting_date="2026-06-20",
    updated_at="2026-05-17T00:00:00Z",
):
    return {
        "source_native_event_id": source_native_event_id,
        "bond_code": bond_code,
        "announcement_date": announcement_date,
        "delisting_date": delisting_date,
        "source": "tushare",
        "updated_at": updated_at,
    }


def _manual_command_row(
    command="DECLARE",
    bond_code="999999.SH",
    announcement_date="2026-05-17",
    delisting_date="2026-07-01",
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


def _write_baseline_state(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "last_successful_sync": "2026-05-16T00:00:00Z",
                "version": "1.0",
                "previous_id_set": ["BASELINE"],
            }
        ),
        encoding="utf-8",
    )


def _fetcher(tmp_path, provider, today="2026-05-17"):
    state_path = tmp_path / "data" / "redemption_fetcher_state.json"
    _write_baseline_state(state_path)
    return RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "data" / "redemption_event_facts_import.csv"),
        ledger_csv_path=str(tmp_path / "data" / "redemption_event_ledger.csv"),
        canonical_csv_path=str(tmp_path / "data" / "canonical_redemption_state.csv"),
        trace_json_path=str(tmp_path / "data" / "reports" / "redemption_event_trace.json"),
        rejected_trace_path=str(tmp_path / "data" / "reports" / "redemption_fetcher_rejected.json"),
        state_path=str(state_path),
        freshness_report_path=str(tmp_path / "data" / "reports" / "freshness_report.json"),
        manual_events_path=str(tmp_path / "data" / "manual_events.csv"),
        manual_review_completions_path=str(tmp_path / "data" / "manual_review_completions.json"),
        manual_degraded_import_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_redemption_event_facts_import.csv"),
        manual_degraded_effective_state_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_effective_redemption_state.csv"),
        manual_degraded_ledger_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_redemption_event_ledger.csv"),
        manual_degraded_canonical_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_canonical_redemption_state.csv"),
        manual_degraded_trace_json_path=str(tmp_path / "data" / "reports" / "manual_degraded_redemption_event_trace.json"),
        today_fn=lambda: today,
    )


def _write_stale_degraded_artifacts(fetcher):
    stale_artifacts = {
        fetcher.manual_degraded_import_csv_path: (
            "source_native_event_id,bond_code,announcement_date,delisting_date,source,updated_at\n"
            "MANUAL_ONLY,999999.SH,2026-05-17,2026-07-01,manual,2026-05-17T10:00:00Z\n"
        ),
        fetcher.manual_degraded_effective_state_csv_path: (
            "date,bond_code,redeem_risk,representative_event_id,representative_revision\n"
            "2026-05-17,999999.SH,True,manual:MANUAL_ONLY,0\n"
        ),
        fetcher.manual_degraded_ledger_csv_path: (
            ",".join(LEDGER_COLUMNS)
            + "\nmanual:MANUAL_ONLY,0,True,ACTIVE,MANUAL_ONLY,999999.SH,2026-05-17,2026-07-01,manual,2026-05-17T10:00:00Z\n"
        ),
        fetcher.manual_degraded_canonical_csv_path: (
            "date,bond_code,redeem_risk,representative_event_id,representative_revision,conflict_count,resolution_mode\n"
            "2026-05-17,999999.SH,True,manual:MANUAL_ONLY,0,0,single_active_event\n"
        ),
        fetcher.manual_degraded_trace_json_path: json.dumps(
            {"pipeline_status": "MANUAL_DEGRADED", "source_mode": "manual_fallback"}
        ),
    }
    for artifact_path, content in stale_artifacts.items():
        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _assert_no_degraded_operational_artifacts(fetcher):
    for artifact_path in fetcher._manual_degraded_operational_artifact_paths():
        assert not Path(artifact_path).exists()


def _freshness_payload(fetcher):
    return json.loads(Path(fetcher.freshness_report_path).read_text(encoding="utf-8"))


def _read_ledger(fetcher):
    return pd.read_csv(fetcher.ledger_csv_path, dtype=str, keep_default_na=False)


def _read_canonical(fetcher):
    return pd.read_csv(fetcher.canonical_csv_path, dtype=str, keep_default_na=False)


def test_authoritative_tushare_recovery_replaces_or_clears_degraded_operational_state(tmp_path):
    provider = StubProvider(result=_mapped_result([_tushare_row()]))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])
    _write_stale_degraded_artifacts(fetcher)

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "OK"
    _assert_no_degraded_operational_artifacts(fetcher)
    ledger = _read_ledger(fetcher)
    canonical = _read_canonical(fetcher)
    trace = json.loads(Path(fetcher.trace_json_path).read_text(encoding="utf-8"))
    assert ledger["source"].tolist() == ["tushare"]
    assert ledger["event_id"].tolist() == ["tushare:TUSHARE_20260517"]
    assert canonical["bond_code"].tolist() == ["118033.SH"]
    assert trace["ingress_artifact_path"] == fetcher.import_csv_path


def test_recovery_future_runs_do_not_consume_stale_degraded_artifacts(tmp_path):
    provider = StubProvider(result=_mapped_result([_tushare_row()]))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])
    _write_stale_degraded_artifacts(fetcher)

    first_result = fetcher.run_redemption_sync_pipeline()
    second_result = fetcher.run_redemption_sync_pipeline()

    assert first_result.status == "OK"
    assert second_result.status == "OK"
    _assert_no_degraded_operational_artifacts(fetcher)
    ledger = _read_ledger(fetcher)
    assert set(ledger["source"]) == {"tushare"}
    assert "manual:MANUAL_ONLY" not in set(ledger["event_id"])
    assert provider.calls == [("2019-01-01", "2026-05-17"), ("2019-01-01", "2026-05-17")]


def test_recovery_does_not_merge_manual_rows_into_durable_truth(tmp_path):
    provider = StubProvider(result=_mapped_result([_tushare_row(source_native_event_id="AUTH_ONLY")]))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row(bond_code="999999.SH")])
    _write_stale_degraded_artifacts(fetcher)

    result = fetcher.run_redemption_sync_pipeline()

    assert result.status == "OK"
    ledger = _read_ledger(fetcher)
    canonical = _read_canonical(fetcher)
    assert ledger["source_native_event_id"].tolist() == ["AUTH_ONLY"]
    assert ledger["source"].tolist() == ["tushare"]
    assert "999999.SH" not in set(ledger["bond_code"])
    assert "999999.SH" not in set(canonical["bond_code"])


def test_recovery_status_restores_normal_authoritative_semantics(tmp_path):
    provider = StubProvider(result=_mapped_result([_tushare_row()]))
    fetcher = _fetcher(tmp_path, provider)
    _write_stale_degraded_artifacts(fetcher)

    result = fetcher.run_redemption_sync_pipeline()
    freshness = _freshness_payload(fetcher)

    assert result.success is True
    assert result.status == "OK"
    assert freshness["pipeline_status"] == "NORMAL"
    assert freshness["pipeline_status"] not in {"MANUAL_DEGRADED", "MANUAL_NO_EVENTS"}


def test_recovery_does_not_require_manual_tushare_convergence_or_supersede_logic(tmp_path):
    provider = StubProvider(result=_mapped_result([_tushare_row()]))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])
    _write_stale_degraded_artifacts(fetcher)

    result = fetcher.run_redemption_sync_pipeline()

    assert result.status == "OK"
    ledger = _read_ledger(fetcher)
    serialized_ledger = ledger.to_csv(index=False)
    assert "SUPERSEDED" not in serialized_ledger
    assert "takeover" not in serialized_ledger.lower()
    assert "manual override" not in serialized_ledger.lower()
    assert set(ledger["revision_reason"]) == {"ACTIVE"}
    assert set(ledger["source"]) == {"tushare"}


def test_recovery_preserves_manual_audit_trail_without_turning_it_into_truth(tmp_path):
    provider = StubProvider(result=_mapped_result([_tushare_row()]))
    fetcher = _fetcher(tmp_path, provider)
    manual_events_path = tmp_path / "data" / "manual_events.csv"
    _write_manual_events(manual_events_path, [_manual_command_row()])
    manual_before = manual_events_path.read_text(encoding="utf-8")
    _write_stale_degraded_artifacts(fetcher)

    result = fetcher.run_redemption_sync_pipeline()

    assert result.status == "OK"
    assert manual_events_path.read_text(encoding="utf-8") == manual_before
    ledger = _read_ledger(fetcher)
    assert set(ledger["source"]) == {"tushare"}
    assert "manual" not in set(ledger["source"])


def test_existing_wave3_identity_contract_unchanged_by_recovery():
    ingress = pd.DataFrame([_tushare_row(source_native_event_id="NATIVE_001")], columns=IMPORT_COLUMNS)

    ledger, rejected = process_ingress_to_ledger(ingress, pd.DataFrame(columns=LEDGER_COLUMNS))

    assert rejected == []
    assert ledger["event_id"].tolist() == ["tushare:NATIVE_001"]
    assert ledger["event_id"].tolist() != ["NATIVE_001"]


def test_recovery_can_follow_an_actual_event_bearing_degraded_run(tmp_path):
    degraded_provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, degraded_provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    degraded_result = fetcher.run_redemption_sync_pipeline()
    assert degraded_result.status == "MANUAL_DEGRADED"
    assert Path(fetcher.manual_degraded_ledger_csv_path).exists()

    fetcher.provider = StubProvider(result=_mapped_result([_tushare_row()]))
    recovery_result = fetcher.run_redemption_sync_pipeline()

    assert recovery_result.status == "OK"
    _assert_no_degraded_operational_artifacts(fetcher)
    ledger = _read_ledger(fetcher)
    assert ledger["source"].tolist() == ["tushare"]
