import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from etl.redemption_pipeline import run_redemption_wave3_pipeline
from etl.tushare_provider import IMPORT_COLUMNS, TuShareProvider

FETCHER_STATE_PATH = "data/redemption_fetcher_state.json"
IMPORT_CSV_PATH = "data/redemption_event_facts_import.csv"
LEDGER_CSV_PATH = "data/redemption_event_ledger.csv"
CANONICAL_CSV_PATH = "data/canonical_redemption_state.csv"
TRACE_JSON_PATH = "data/reports/redemption_event_trace.json"
REJECTED_TRACE_PATH = "data/reports/redemption_fetcher_rejected.json"
FRESHNESS_REPORT_PATH = "data/reports/freshness_report.json"
BOOTSTRAP_START_DATE = "2019-01-01"
SOURCE_TUSHARE = "tushare"
TRACKER_LAST_SUCCESSFUL_SYNC = "last_successful_sync"
TRACKER_VERSION = "version"
TRACKER_PREVIOUS_ID_SET = "previous_id_set"
STATE_TRACKER_VERSION = "1.0"


@dataclass
class FetchResult:
    success: bool
    status: str
    row_count: int
    rejected_count: int


@dataclass
class PipelineResult:
    success: bool
    status: str
    ingress_count: int
    ledger_event_count: int
    canonical_date_count: int
    disappearance_warning: dict | None


class RedemptionFetcher:
    def __init__(
        self,
        provider: TuShareProvider,
        import_csv_path: str = IMPORT_CSV_PATH,
        ledger_csv_path: str = LEDGER_CSV_PATH,
        canonical_csv_path: str = CANONICAL_CSV_PATH,
        trace_json_path: str = TRACE_JSON_PATH,
        rejected_trace_path: str = REJECTED_TRACE_PATH,
        state_path: str = FETCHER_STATE_PATH,
        freshness_report_path: str = FRESHNESS_REPORT_PATH,
        today_fn: Optional[Callable[[], str]] = None,
    ):
        self.provider = provider
        self.import_csv_path = import_csv_path
        self.ledger_csv_path = ledger_csv_path
        self.canonical_csv_path = canonical_csv_path
        self.trace_json_path = trace_json_path
        self.rejected_trace_path = rejected_trace_path
        self.state_path = state_path
        self.freshness_report_path = freshness_report_path
        self._today_fn = today_fn
        self.filtered_snapshot_ids: list[str] = []

    def _today_str(self) -> str:
        if self._today_fn is not None:
            return self._today_fn()
        return datetime.now().date().isoformat()

    @staticmethod
    def _utc_timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _ensure_parent_dir(path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    @staticmethod
    def _validate_import_columns(df: pd.DataFrame):
        missing_columns = [column for column in IMPORT_COLUMNS if column not in df.columns]
        if missing_columns:
            raise ValueError(
                "Mapped redemption result missing required import columns: "
                + ", ".join(missing_columns)
            )

    @classmethod
    def _reserve_temp_path(cls, target_path: str, suffix: str) -> str:
        cls._ensure_parent_dir(target_path)
        fd, temp_path = tempfile.mkstemp(
            prefix=".tmp_redemption_fetcher_",
            suffix=suffix,
            dir=os.path.dirname(target_path) or ".",
        )
        os.close(fd)
        return temp_path

    @classmethod
    def _stage_csv(cls, df: pd.DataFrame, path: str) -> str:
        temp_path = cls._reserve_temp_path(path, ".csv")
        try:
            df.to_csv(temp_path, index=False)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
        return temp_path

    @classmethod
    def _stage_json(cls, payload, path: str) -> str:
        temp_path = cls._reserve_temp_path(path, ".json")
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
        return temp_path

    @classmethod
    def _backup_target(cls, target_path: str) -> Optional[str]:
        if not os.path.exists(target_path):
            return None

        suffix = os.path.splitext(target_path)[1] or ".bak"
        backup_path = cls._reserve_temp_path(target_path, suffix)
        os.unlink(backup_path)
        os.replace(target_path, backup_path)
        return backup_path

    @classmethod
    def _publish_staged_artifacts(cls, staged_artifacts: list[tuple[str, str]]):
        backups: dict[str, Optional[str]] = {}
        try:
            for _, target_path in staged_artifacts:
                backups[target_path] = cls._backup_target(target_path)

            for staged_path, target_path in staged_artifacts:
                os.replace(staged_path, target_path)
        except Exception:
            for staged_path, _ in staged_artifacts:
                if os.path.exists(staged_path):
                    os.unlink(staged_path)

            for _, target_path in reversed(staged_artifacts):
                if os.path.exists(target_path):
                    os.unlink(target_path)

                backup_path = backups.get(target_path)
                if backup_path and os.path.exists(backup_path):
                    os.replace(backup_path, target_path)
            raise
        else:
            for backup_path in backups.values():
                if backup_path and os.path.exists(backup_path):
                    os.unlink(backup_path)

    def _read_state_tracker(self) -> dict:
        if not os.path.exists(self.state_path):
            return {
                TRACKER_LAST_SUCCESSFUL_SYNC: None,
                TRACKER_VERSION: STATE_TRACKER_VERSION,
                TRACKER_PREVIOUS_ID_SET: [],
            }

        with open(self.state_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        previous_id_set = payload.get(TRACKER_PREVIOUS_ID_SET) or []
        return {
            TRACKER_LAST_SUCCESSFUL_SYNC: payload.get(TRACKER_LAST_SUCCESSFUL_SYNC),
            TRACKER_VERSION: payload.get(TRACKER_VERSION, STATE_TRACKER_VERSION),
            TRACKER_PREVIOUS_ID_SET: [str(item) for item in previous_id_set],
        }

    def _write_state_tracker(self, previous_id_set: list[str], last_successful_sync: str):
        payload = {
            TRACKER_LAST_SUCCESSFUL_SYNC: last_successful_sync,
            TRACKER_VERSION: STATE_TRACKER_VERSION,
            TRACKER_PREVIOUS_ID_SET: [str(item) for item in previous_id_set],
        }
        staged_state_path = self._stage_json(payload, self.state_path)
        self._publish_staged_artifacts([(staged_state_path, self.state_path)])

    def _write_freshness_report(self, pipeline_status: str, disappearance_warning: dict | None):
        payload = {
            "generated_at": self._utc_timestamp(),
            "pipeline_status": pipeline_status,
            "empty_snapshot_warning": None,
            "disappearance_warning": disappearance_warning,
        }
        staged_report_path = self._stage_json(payload, self.freshness_report_path)
        self._publish_staged_artifacts([(staged_report_path, self.freshness_report_path)])

    @staticmethod
    def _read_artifact_row_count(path: str) -> int:
        if not os.path.exists(path):
            return 0
        return len(pd.read_csv(path, dtype=str, keep_default_na=False))

    def _build_disappearance_warning(self, previous_id_set: list[str]) -> dict | None:
        previous_ids = {str(item) for item in previous_id_set if str(item)}
        current_ids = {str(item) for item in self.filtered_snapshot_ids if str(item)}
        missing_ids = sorted(previous_ids - current_ids)
        if not missing_ids:
            return None

        return {
            "missing_ids": missing_ids,
            "previous_count": len(previous_ids),
            "current_count": len(current_ids),
        }

    def fetch_and_build_import_csv(self, import_csv_path: Optional[str] = None) -> FetchResult:
        target_import_csv_path = import_csv_path or self.import_csv_path

        try:
            mapped_result = self.provider.fetch_and_map_redemption_events(
                BOOTSTRAP_START_DATE,
                self._today_str(),
            )
        except Exception:
            return FetchResult(
                success=False,
                status="API_FAILED",
                row_count=0,
                rejected_count=0,
            )

        self.filtered_snapshot_ids = list(mapped_result.filtered_snapshot_ids)
        admitted_df = mapped_result.df.copy()
        rejected_duplicates = list(mapped_result.rejected_duplicates)

        if admitted_df.empty:
            if rejected_duplicates:
                staged_rejected_trace_path = self._stage_json(
                    rejected_duplicates,
                    self.rejected_trace_path,
                )
                self._publish_staged_artifacts(
                    [(staged_rejected_trace_path, self.rejected_trace_path)]
                )

            return FetchResult(
                success=False,
                status="EMPTY_ABORT",
                row_count=0,
                rejected_count=len(rejected_duplicates),
            )

        self._validate_import_columns(admitted_df)
        admitted_df = admitted_df[IMPORT_COLUMNS].fillna("")
        staged_import_csv_path = self._stage_csv(admitted_df, target_import_csv_path)
        staged_rejected_trace_path = self._stage_json(
            rejected_duplicates,
            self.rejected_trace_path,
        )
        self._publish_staged_artifacts(
            [
                (staged_import_csv_path, target_import_csv_path),
                (staged_rejected_trace_path, self.rejected_trace_path),
            ]
        )

        return FetchResult(
            success=True,
            status="OK",
            row_count=len(admitted_df),
            rejected_count=len(rejected_duplicates),
        )

    def run_redemption_sync_pipeline(self) -> PipelineResult:
        fetch_result = self.fetch_and_build_import_csv()
        if not fetch_result.success:
            return PipelineResult(
                success=False,
                status="EMPTY_ABORT" if fetch_result.status == "EMPTY_ABORT" else "FETCH_FAILED",
                ingress_count=fetch_result.row_count,
                ledger_event_count=0,
                canonical_date_count=0,
                disappearance_warning=None,
            )

        today = self._today_str()
        target_dates = self.provider.fetch_trade_calendar(BOOTSTRAP_START_DATE, today)

        try:
            run_redemption_wave3_pipeline(
                import_csv_path=self.import_csv_path,
                ledger_csv_path=self.ledger_csv_path,
                canonical_csv_path=self.canonical_csv_path,
                trace_json_path=self.trace_json_path,
                target_dates=target_dates,
            )
        except Exception:
            return PipelineResult(
                success=False,
                status="WAVE3_FAILED",
                ingress_count=fetch_result.row_count,
                ledger_event_count=0,
                canonical_date_count=0,
                disappearance_warning=None,
            )

        tracker_state = self._read_state_tracker()
        disappearance_warning = self._build_disappearance_warning(
            tracker_state[TRACKER_PREVIOUS_ID_SET]
        )
        self._write_freshness_report(
            pipeline_status="NORMAL",
            disappearance_warning=disappearance_warning,
        )

        current_previous_id_set = sorted(
            {str(item) for item in self.filtered_snapshot_ids if str(item)}
        )
        last_successful_sync = self._utc_timestamp()
        self._write_state_tracker(
            previous_id_set=current_previous_id_set,
            last_successful_sync=last_successful_sync,
        )

        return PipelineResult(
            success=True,
            status="OK",
            ingress_count=fetch_result.row_count,
            ledger_event_count=self._read_artifact_row_count(self.ledger_csv_path),
            canonical_date_count=self._read_artifact_row_count(self.canonical_csv_path),
            disappearance_warning=disappearance_warning,
        )
