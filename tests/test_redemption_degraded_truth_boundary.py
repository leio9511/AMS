import json

import pandas as pd

from etl.cb_provider_base import DataProviderNetworkUnavailableError
from etl.redemption_fetcher import RedemptionFetcher
from etl.redemption_ledger import IMPORT_COLUMNS, LEDGER_COLUMNS, process_ingress_to_ledger
from etl.tushare_provider import MappedRedemptionResult


class StubProvider:
    def __init__(self, result=None, error=None, trade_calendar_result=None):
        self.result = result
        self.error = error
        self.trade_calendar_result = trade_calendar_result or []

    def fetch_and_map_redemption_events(self, start_date, end_date):
        if self.error is not None:
            raise self.error
        return self.result

    def fetch_trade_calendar(self, start_date, end_date):
        return list(self.trade_calendar_result)


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


def _fetcher(tmp_path, provider):
    state_path = tmp_path / "data" / "state.json"
    _write_baseline_state(state_path)
    return RedemptionFetcher(
        provider=provider,
        import_csv_path=str(tmp_path / "data" / "manual_degraded_import.csv"),
        ledger_csv_path=str(tmp_path / "data" / "redemption_event_ledger.csv"),
        canonical_csv_path=str(tmp_path / "data" / "canonical_redemption_state.csv"),
        trace_json_path=str(tmp_path / "data" / "reports" / "redemption_event_trace.json"),
        rejected_trace_path=str(tmp_path / "data" / "reports" / "rejected.json"),
        state_path=str(state_path),
        freshness_report_path=str(tmp_path / "data" / "reports" / "freshness_report.json"),
        manual_events_path=str(tmp_path / "data" / "manual_events.csv"),
        manual_review_completions_path=str(tmp_path / "data" / "manual_review_completions.json"),
        manual_degraded_import_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_redemption_event_facts_import.csv"),
        manual_degraded_ledger_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_redemption_event_ledger.csv"),
        manual_degraded_canonical_csv_path=str(tmp_path / "data" / "reports" / "manual_degraded_canonical_redemption_state.csv"),
        manual_degraded_trace_json_path=str(tmp_path / "data" / "reports" / "manual_degraded_redemption_event_trace.json"),
        today_fn=lambda: "2026-05-17",
    )


def _run_event_bearing_degraded(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])
    result = fetcher.run_redemption_sync_pipeline()
    return fetcher, result


def _seed_durable_truth(fetcher):
    ledger_content = (
        ",".join(LEDGER_COLUMNS)
        + "\n"
        + "tushare:BASELINE,0,True,ACTIVE,BASELINE,BASELINE.SH,2026-05-16,2026-06-16,tushare,2026-05-16T00:00:00Z\n"
    )
    canonical_content = (
        "date,bond_code,redeem_risk,representative_event_id,representative_revision,conflict_count,resolution_mode\n"
        "2026-05-16,BASELINE.SH,True,tushare:BASELINE,0,0,single_active_event\n"
    )
    trace_content = json.dumps({"pipeline_status": "NORMAL", "marker": "do-not-touch"}, indent=2)
    for path, content in [
        (fetcher.ledger_csv_path, ledger_content),
        (fetcher.canonical_csv_path, canonical_content),
        (fetcher.trace_json_path, trace_content),
    ]:
        p = tmp_path_from_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def tmp_path_from_path(path):
    from pathlib import Path

    return Path(path)


def _read_bytes(path):
    return tmp_path_from_path(path).read_bytes()


def test_manual_degraded_run_does_not_mutate_existing_durable_ledger_or_canonical(tmp_path):
    provider = StubProvider(error=DataProviderNetworkUnavailableError("network down"))
    fetcher = _fetcher(tmp_path, provider)
    _seed_durable_truth(fetcher)
    before = {
        fetcher.ledger_csv_path: _read_bytes(fetcher.ledger_csv_path),
        fetcher.canonical_csv_path: _read_bytes(fetcher.canonical_csv_path),
        fetcher.trace_json_path: _read_bytes(fetcher.trace_json_path),
    }
    _write_manual_events(tmp_path / "data" / "manual_events.csv", [_manual_command_row()])

    result = fetcher.run_redemption_sync_pipeline()

    assert result.success is True
    assert result.status == "MANUAL_DEGRADED"
    for path, content in before.items():
        assert _read_bytes(path) == content


def test_manual_degraded_run_does_not_create_durable_truth_when_absent(tmp_path):
    fetcher, result = _run_event_bearing_degraded(tmp_path)

    assert result.success is True
    assert result.status == "MANUAL_DEGRADED"
    assert not tmp_path_from_path(fetcher.ledger_csv_path).exists()
    assert not tmp_path_from_path(fetcher.canonical_csv_path).exists()
    assert not tmp_path_from_path(fetcher.trace_json_path).exists()


def test_manual_degraded_run_writes_only_degraded_scoped_operational_artifacts(tmp_path):
    fetcher, result = _run_event_bearing_degraded(tmp_path)

    assert result.status == "MANUAL_DEGRADED"
    assert tmp_path_from_path(fetcher.manual_degraded_import_csv_path).exists()
    assert tmp_path_from_path(fetcher.manual_degraded_ledger_csv_path).exists()
    assert tmp_path_from_path(fetcher.manual_degraded_canonical_csv_path).exists()
    assert tmp_path_from_path(fetcher.manual_degraded_trace_json_path).exists()
    assert tmp_path_from_path(fetcher.freshness_report_path).exists()
    assert not tmp_path_from_path(fetcher.ledger_csv_path).exists()
    assert not tmp_path_from_path(fetcher.canonical_csv_path).exists()
    assert not tmp_path_from_path(fetcher.trace_json_path).exists()

    degraded_ledger = pd.read_csv(fetcher.manual_degraded_ledger_csv_path, dtype=str, keep_default_na=False)
    assert degraded_ledger["source"].tolist() == ["manual"]
    assert degraded_ledger["event_id"].tolist() == ["manual:123456.SH_2026-05-17"]
    assert "manual_truth" not in "\n".join(str(p) for p in (tmp_path / "data").rglob("*"))


def test_degraded_status_never_reported_as_normal_success(tmp_path):
    fetcher, result = _run_event_bearing_degraded(tmp_path)

    assert result.success is True
    assert result.status == "MANUAL_DEGRADED"
    freshness = json.loads(tmp_path_from_path(fetcher.freshness_report_path).read_text(encoding="utf-8"))
    assert freshness["pipeline_status"] == "MANUAL_DEGRADED"
    assert freshness["pipeline_status"] not in {"NORMAL", "OK"}
    trace = json.loads(tmp_path_from_path(fetcher.manual_degraded_trace_json_path).read_text(encoding="utf-8"))
    assert trace.get("pipeline_status") != "NORMAL"
    assert trace.get("pipeline_status") != "OK"


def test_existing_wave3_identity_contract_unchanged_by_degraded_artifact_isolation():
    ingress = pd.DataFrame(
        [
            {
                "source_native_event_id": "NATIVE_001",
                "bond_code": "118033",
                "announcement_date": "2026-05-17",
                "delisting_date": "2026-06-20",
                "source": "tushare",
                "updated_at": "2026-05-17T00:00:00Z",
            }
        ],
        columns=IMPORT_COLUMNS,
    )

    ledger, rejected = process_ingress_to_ledger(ingress, pd.DataFrame(columns=LEDGER_COLUMNS))

    assert rejected == []
    assert ledger["event_id"].tolist() == ["tushare:NATIVE_001"]
    assert ledger["event_id"].tolist() != ["NATIVE_001"]
