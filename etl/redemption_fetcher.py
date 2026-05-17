import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from etl.cb_provider_base import DataProviderError, DataProviderFailureStatus
from etl.manual_event_injector import load_and_reduce_manual_events
from etl.redemption_pipeline import run_redemption_wave3_pipeline
from etl.tushare_provider import IMPORT_COLUMNS, TuShareProvider

FETCHER_STATE_PATH = "data/redemption_fetcher_state.json"
IMPORT_CSV_PATH = "data/redemption_event_facts_import.csv"
LEDGER_CSV_PATH = "data/redemption_event_ledger.csv"
CANONICAL_CSV_PATH = "data/canonical_redemption_state.csv"
TRACE_JSON_PATH = "data/reports/redemption_event_trace.json"
REJECTED_TRACE_PATH = "data/reports/redemption_fetcher_rejected.json"
FRESHNESS_REPORT_PATH = "data/reports/freshness_report.json"
MANUAL_EVENTS_PATH = "data/manual_events.csv"
MANUAL_REVIEW_COMPLETIONS_PATH = "data/manual_review_completions.json"
MANUAL_DEGRADED_IMPORT_CSV_PATH = "data/reports/manual_degraded_redemption_event_facts_import.csv"
MANUAL_DEGRADED_LEDGER_CSV_PATH = "data/reports/manual_degraded_redemption_event_ledger.csv"
MANUAL_DEGRADED_CANONICAL_CSV_PATH = "data/reports/manual_degraded_canonical_redemption_state.csv"
MANUAL_DEGRADED_TRACE_JSON_PATH = "data/reports/manual_degraded_redemption_event_trace.json"
BOOTSTRAP_START_DATE = "2019-01-01"
SOURCE_TUSHARE = "tushare"
STATUS_MANUAL_DEGRADED = "MANUAL_DEGRADED"
STATUS_FRESHNESS_EMPTY = "FRESHNESS_EMPTY"
STATUS_MANUAL_NO_EVENTS = "MANUAL_NO_EVENTS"
STATUS_BOOTSTRAP_REQUIRED = "BOOTSTRAP_REQUIRED"
TRACKER_LAST_SUCCESSFUL_SYNC = "last_successful_sync"
TRACKER_VERSION = "version"
TRACKER_PREVIOUS_ID_SET = "previous_id_set"
STATE_TRACKER_VERSION = "1.0"
EMPTY_SNAPSHOT_WARNING_MESSAGE = "全量历史 pull 返回 0 行，预期 ~2000 行"
EMPTY_SNAPSHOT_WARNING_SUGGESTED_ACTION = "检查 TuShare API 状态，确认数据是否正确"


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
        manual_events_path: str = MANUAL_EVENTS_PATH,
        manual_review_completions_path: str = MANUAL_REVIEW_COMPLETIONS_PATH,
        manual_degraded_import_csv_path: str = MANUAL_DEGRADED_IMPORT_CSV_PATH,
        manual_degraded_ledger_csv_path: str = MANUAL_DEGRADED_LEDGER_CSV_PATH,
        manual_degraded_canonical_csv_path: str = MANUAL_DEGRADED_CANONICAL_CSV_PATH,
        manual_degraded_trace_json_path: str = MANUAL_DEGRADED_TRACE_JSON_PATH,
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
        self.manual_events_path = manual_events_path
        self.manual_review_completions_path = manual_review_completions_path
        self.manual_degraded_import_csv_path = manual_degraded_import_csv_path
        self.manual_degraded_ledger_csv_path = manual_degraded_ledger_csv_path
        self.manual_degraded_canonical_csv_path = manual_degraded_canonical_csv_path
        self.manual_degraded_trace_json_path = manual_degraded_trace_json_path
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

    @staticmethod
    def _backup_sidecar_path(target_path: str) -> str:
        return f"{target_path}.bak"

    @staticmethod
    def _delete_if_exists(path: str):
        if os.path.exists(path):
            os.unlink(path)

    def _wave3_truth_source_paths(self) -> list[str]:
        return [
            self.ledger_csv_path,
            self.canonical_csv_path,
            self.trace_json_path,
        ]

    def _create_wave3_backups(self) -> dict[str, bool]:
        backup_state: dict[str, bool] = {}
        for target_path in self._wave3_truth_source_paths():
            backup_path = self._backup_sidecar_path(target_path)
            self._delete_if_exists(backup_path)

            existed_before_run = os.path.exists(target_path)
            backup_state[target_path] = existed_before_run
            if existed_before_run:
                self._ensure_parent_dir(backup_path)
                shutil.copyfile(target_path, backup_path)

        return backup_state

    def _discard_wave3_backups(self, backup_state: dict[str, bool]):
        for target_path in backup_state:
            self._delete_if_exists(self._backup_sidecar_path(target_path))

    def _restore_wave3_truth_sources(self, backup_state: dict[str, bool]):
        for target_path, existed_before_run in backup_state.items():
            backup_path = self._backup_sidecar_path(target_path)
            if existed_before_run:
                if os.path.exists(target_path):
                    os.unlink(target_path)
                os.replace(backup_path, target_path)
            else:
                self._delete_if_exists(target_path)
                self._delete_if_exists(backup_path)

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

    def _write_freshness_report(
        self,
        pipeline_status: str,
        disappearance_warning: dict | None,
        empty_snapshot_warning: dict | None = None,
    ):
        payload = {
            "generated_at": self._utc_timestamp(),
            "pipeline_status": pipeline_status,
            "empty_snapshot_warning": empty_snapshot_warning,
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

    def _build_empty_snapshot_warning(self) -> dict | None:
        if self.filtered_snapshot_ids:
            return None

        return {
            "message": EMPTY_SNAPSHOT_WARNING_MESSAGE,
            "suggested_action": EMPTY_SNAPSHOT_WARNING_SUGGESTED_ACTION,
        }

    def _has_authoritative_baseline(self) -> bool:
        tracker_state = self._read_state_tracker()
        if tracker_state.get(TRACKER_LAST_SUCCESSFUL_SYNC):
            return True

        for path in [self.ledger_csv_path, self.canonical_csv_path]:
            if self._read_artifact_row_count(path) > 0:
                return True
        return False

    def _read_manual_fallback_for_target_date(self, target_date: str) -> pd.DataFrame:
        manual_df = load_and_reduce_manual_events(
            self.manual_events_path,
            updated_at=self._utc_timestamp(),
        )
        self._validate_import_columns(manual_df)
        manual_df = manual_df[IMPORT_COLUMNS].fillna("")
        return manual_df[manual_df["announcement_date"].astype(str) == target_date].reset_index(drop=True)

    def _has_manual_review_completion(self, target_date: str) -> bool:
        if not os.path.exists(self.manual_review_completions_path):
            return False
        with open(self.manual_review_completions_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            return False
        return any(
            str(item.get("announcement_date", "")).strip() == target_date
            for item in payload
            if isinstance(item, dict)
        )

    def _pipeline_result_with_status(
        self,
        status: str,
        success: bool = False,
        ingress_count: int = 0,
        ledger_csv_path: Optional[str] = None,
        canonical_csv_path: Optional[str] = None,
    ) -> PipelineResult:
        self._write_freshness_report(
            pipeline_status=status,
            disappearance_warning=None,
        )
        ledger_count_path = ledger_csv_path or self.ledger_csv_path
        canonical_count_path = canonical_csv_path or self.canonical_csv_path
        return PipelineResult(
            success=success,
            status=status,
            ingress_count=ingress_count,
            ledger_event_count=self._read_artifact_row_count(ledger_count_path) if success else 0,
            canonical_date_count=self._read_artifact_row_count(canonical_count_path) if success else 0,
            disappearance_warning=None,
        )

    def _handle_network_fallback(self, target_date: str) -> PipelineResult:
        if not self._has_authoritative_baseline():
            return self._pipeline_result_with_status(STATUS_BOOTSTRAP_REQUIRED)

        try:
            manual_df = self._read_manual_fallback_for_target_date(target_date)
            if manual_df.empty:
                if self._has_manual_review_completion(target_date):
                    return self._pipeline_result_with_status(STATUS_MANUAL_NO_EVENTS, success=True)
                return self._pipeline_result_with_status(STATUS_FRESHNESS_EMPTY)
        except Exception:
            return self._pipeline_result_with_status(DataProviderFailureStatus.RUNTIME_BUG.value)

        staged_import_csv_path = self._stage_csv(manual_df, self.manual_degraded_import_csv_path)
        self._publish_staged_artifacts([(staged_import_csv_path, self.manual_degraded_import_csv_path)])
        self._delete_if_exists(self.manual_degraded_ledger_csv_path)
        self._delete_if_exists(self.manual_degraded_canonical_csv_path)
        self._delete_if_exists(self.manual_degraded_trace_json_path)

        try:
            run_redemption_wave3_pipeline(
                import_csv_path=self.manual_degraded_import_csv_path,
                ledger_csv_path=self.manual_degraded_ledger_csv_path,
                canonical_csv_path=self.manual_degraded_canonical_csv_path,
                trace_json_path=self.manual_degraded_trace_json_path,
                target_dates=[target_date],
            )
        except Exception:
            self._delete_if_exists(self.manual_degraded_import_csv_path)
            self._delete_if_exists(self.manual_degraded_ledger_csv_path)
            self._delete_if_exists(self.manual_degraded_canonical_csv_path)
            self._delete_if_exists(self.manual_degraded_trace_json_path)
            self._write_freshness_report(
                pipeline_status="WAVE3_FAILED",
                disappearance_warning=None,
            )
            return PipelineResult(
                success=False,
                status="WAVE3_FAILED",
                ingress_count=len(manual_df),
                ledger_event_count=0,
                canonical_date_count=0,
                disappearance_warning=None,
            )

        return self._pipeline_result_with_status(
            STATUS_MANUAL_DEGRADED,
            success=True,
            ingress_count=len(manual_df),
            ledger_csv_path=self.manual_degraded_ledger_csv_path,
            canonical_csv_path=self.manual_degraded_canonical_csv_path,
        )

    def fetch_and_build_import_csv(
        self,
        import_csv_path: Optional[str] = None,
        today_str: Optional[str] = None,
    ) -> FetchResult:
        target_import_csv_path = import_csv_path or self.import_csv_path
        fetch_today = today_str or self._today_str()

        try:
            mapped_result = self.provider.fetch_and_map_redemption_events(
                BOOTSTRAP_START_DATE,
                fetch_today,
            )
        except DataProviderError as exc:
            return FetchResult(
                success=False,
                status=exc.status,
                row_count=0,
                rejected_count=0,
            )
        except Exception:
            return FetchResult(
                success=False,
                status=DataProviderFailureStatus.RUNTIME_BUG.value,
                row_count=0,
                rejected_count=0,
            )

        self.filtered_snapshot_ids = list(mapped_result.filtered_snapshot_ids)
        admitted_df = mapped_result.df.copy()
        rejected_duplicates = list(mapped_result.rejected_duplicates)

        if admitted_df.empty:
            if not self.filtered_snapshot_ids:
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

            admitted_df = pd.DataFrame(columns=IMPORT_COLUMNS)

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
        today = self._today_str()
        fetch_result = self.fetch_and_build_import_csv(today_str=today)
        if not fetch_result.success:
            if fetch_result.status == "EMPTY_ABORT":
                self._write_freshness_report(
                    pipeline_status="EMPTY_ABORT",
                    disappearance_warning=None,
                    empty_snapshot_warning=self._build_empty_snapshot_warning(),
                )

            explicit_statuses = {
                DataProviderFailureStatus.AUTH_FAILED.value,
                DataProviderFailureStatus.QUOTA_EXCEEDED.value,
                DataProviderFailureStatus.RUNTIME_BUG.value,
            }
            if fetch_result.status == DataProviderFailureStatus.NETWORK_UNAVAILABLE.value:
                return self._handle_network_fallback(today)
            if fetch_result.status in explicit_statuses:
                return self._pipeline_result_with_status(fetch_result.status)

            return PipelineResult(
                success=False,
                status="EMPTY_ABORT" if fetch_result.status == "EMPTY_ABORT" else "FETCH_FAILED",
                ingress_count=fetch_result.row_count,
                ledger_event_count=0,
                canonical_date_count=0,
                disappearance_warning=None,
            )

        target_dates = self.provider.fetch_trade_calendar(BOOTSTRAP_START_DATE, today)
        backup_state = self._create_wave3_backups()

        try:
            run_redemption_wave3_pipeline(
                import_csv_path=self.import_csv_path,
                ledger_csv_path=self.ledger_csv_path,
                canonical_csv_path=self.canonical_csv_path,
                trace_json_path=self.trace_json_path,
                target_dates=target_dates,
            )
        except Exception:
            self._restore_wave3_truth_sources(backup_state)
            self._delete_if_exists(self.import_csv_path)
            self._delete_if_exists(self.rejected_trace_path)
            return PipelineResult(
                success=False,
                status="WAVE3_FAILED",
                ingress_count=fetch_result.row_count,
                ledger_event_count=0,
                canonical_date_count=0,
                disappearance_warning=None,
            )

        self._discard_wave3_backups(backup_state)

        tracker_state = self._read_state_tracker()
        disappearance_warning = self._build_disappearance_warning(
            tracker_state[TRACKER_PREVIOUS_ID_SET]
        )
        self._write_freshness_report(
            pipeline_status="NORMAL",
            disappearance_warning=disappearance_warning,
        )

        current_previous_id_set = [
            str(item) for item in self.filtered_snapshot_ids if str(item)
        ]
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
