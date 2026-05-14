import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from etl.tushare_provider import IMPORT_COLUMNS, TuShareProvider

FETCHER_STATE_PATH = "data/redemption_fetcher_state.json"
IMPORT_CSV_PATH = "data/redemption_event_facts_import.csv"
REJECTED_TRACE_PATH = "data/reports/redemption_fetcher_rejected.json"
FRESHNESS_REPORT_PATH = "data/reports/freshness_report.json"
BOOTSTRAP_START_DATE = "2019-01-01"
SOURCE_TUSHARE = "tushare"


@dataclass
class FetchResult:
    success: bool
    status: str
    row_count: int
    rejected_count: int


class RedemptionFetcher:
    def __init__(
        self,
        provider: TuShareProvider,
        import_csv_path: str = IMPORT_CSV_PATH,
        rejected_trace_path: str = REJECTED_TRACE_PATH,
        state_path: str = FETCHER_STATE_PATH,
        freshness_report_path: str = FRESHNESS_REPORT_PATH,
        today_fn: Optional[Callable[[], str]] = None,
    ):
        self.provider = provider
        self.import_csv_path = import_csv_path
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
    def _ensure_parent_dir(path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

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
            return FetchResult(
                success=False,
                status="EMPTY_ABORT",
                row_count=0,
                rejected_count=len(rejected_duplicates),
            )

        admitted_df = admitted_df.reindex(columns=IMPORT_COLUMNS).fillna("")
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
