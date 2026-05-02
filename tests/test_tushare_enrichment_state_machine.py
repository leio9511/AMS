import datetime
import json
import os
import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from etl.cb_provider_base import DataProviderQuotaError
from etl.tushare_enrichment_orchestrator import TuShareEnrichmentOrchestrator


class _StateMachineProvider:
    def __init__(self):
        self._bond_to_stock_map = {
            "113052.SH": "601236.SH",
            "110088.SH": "600000.SH",
        }
        self.pro = MagicMock()
        self.pro.daily.return_value = pd.DataFrame(
            {
                "ts_code": ["601236.SH", "600000.SH"],
                "trade_date": ["20230201", "20230201"],
                "close": [10.0, 20.0],
            }
        )
        self.fetch_cb_price_changes_calls = []

    def fetch_cb_price_changes(self, ticker):
        self.fetch_cb_price_changes_calls.append(ticker)
        return pd.DataFrame(
            {
                "ts_code": [ticker],
                "change_date": ["2023-01-01"],
                "convert_price_initial": [10.0],
                "convertprice_aft": [9.0],
            }
        )

    def fetch_cb_basic(self):
        return pd.DataFrame(
            {
                "code": ["113052.SH", "110088.SH"],
                "conv_price": [10.0, 11.0],
            }
        )

    def fetch_cb_daily(self, tickers, start_date, end_date):
        rows = []
        for ticker in tickers:
            rows.append(
                {
                    "code": ticker,
                    "time": "2023-02-01",
                    "close": 110.0,
                }
            )
        return pd.DataFrame(rows).set_index(["code", "time"])

    def fetch_stock_daily(self, tickers, start_date, end_date):
        return self.pro.daily(
            ts_code=",".join(tickers),
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        ).rename(columns={"ts_code": "stk_code", "trade_date": "time"})


def _write_state(orchestrator, start_date, end_date, state):
    state_path = orchestrator._get_state_path(start_date, end_date)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    return state_path


def test_stale_lock_takeover_applies_even_when_pid_metadata_exists(tmp_path):
    provider = _StateMachineProvider()
    orchestrator = TuShareEnrichmentOrchestrator(provider, cache_dir=str(tmp_path), sleep_seconds_between_calls=0)
    start_date = "2023-02-01"
    end_date = "2023-02-28"
    tickers = ["113052.SH"]

    state_path = _write_state(
        orchestrator,
        start_date,
        end_date,
        {
            "run_status": "RUNNING",
            "provider": "tushare",
            "start_date": start_date,
            "end_date": end_date,
            "sorted_tickers": tickers,
            "completed_tickers": [],
            "pending_tickers": tickers,
            "failed_tickers": [],
            "last_processed_ticker": "",
            "sleep_seconds_between_calls": 0,
            "last_attempt_at": "2023-02-01T00:00:00",
            "next_eligible_at": "",
        },
    )
    stale_mtime = time.time() - (31 * 60)
    os.utime(state_path, (stale_mtime, stale_mtime))

    lock_path = orchestrator._get_lock_path(start_date, end_date)
    old_created_at = (datetime.datetime.now() - datetime.timedelta(hours=7)).isoformat()
    with open(lock_path, "w") as f:
        json.dump(
            {
                "owner_pid": os.getpid(),
                "owner_hostname": "test-host",
                "created_at": old_created_at,
                "run_state_path": state_path,
            },
            f,
        )

    result = orchestrator.run(tickers, start_date, end_date)

    assert not result.empty
    assert provider.fetch_cb_price_changes_calls == ["113052.SH"]
    assert not os.path.exists(lock_path)
    final_state = orchestrator.load_state(start_date, end_date, tickers)
    assert final_state["run_status"] == "COMPLETED"
    assert final_state["completed_tickers"] == ["113052.SH"]


def test_rate_limited_state_persists_next_eligible_at_and_real_sleep_contract(tmp_path):
    provider = _StateMachineProvider()
    provider.fetch_cb_price_changes = MagicMock(side_effect=DataProviderQuotaError("RATE_LIMITED"))
    orchestrator = TuShareEnrichmentOrchestrator(provider, cache_dir=str(tmp_path), sleep_seconds_between_calls=0.25)

    with pytest.raises(DataProviderQuotaError, match="RATE_LIMITED"):
        orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    final_state = orchestrator.load_state("2023-02-01", "2023-02-28", ["113052.SH"])
    assert final_state["run_status"] == "RATE_LIMITED"
    assert final_state["sleep_seconds_between_calls"] == 0.25
    assert final_state["last_attempt_at"]
    assert final_state["next_eligible_at"]
    last_attempt_at = datetime.datetime.fromisoformat(final_state["last_attempt_at"])
    next_eligible_at = datetime.datetime.fromisoformat(final_state["next_eligible_at"])
    assert (next_eligible_at - last_attempt_at).total_seconds() == pytest.approx(0.25)


def test_unrecoverable_failure_transitions_to_failed_without_erasing_completed_work(tmp_path):
    provider = _StateMachineProvider()
    provider.fetch_cb_price_changes = MagicMock(side_effect=RuntimeError("boom"))
    orchestrator = TuShareEnrichmentOrchestrator(provider, cache_dir=str(tmp_path), sleep_seconds_between_calls=0)
    tickers = ["113052.SH", "110088.SH"]
    start_date = "2023-02-01"
    end_date = "2023-02-28"

    orchestrator.save_state(
        {
            "run_status": "PARTIAL_SUCCESS",
            "provider": "tushare",
            "start_date": start_date,
            "end_date": end_date,
            "sorted_tickers": tickers,
            "completed_tickers": ["113052.SH"],
            "pending_tickers": ["110088.SH"],
            "failed_tickers": [],
            "last_processed_ticker": "113052.SH",
            "sleep_seconds_between_calls": 0,
            "last_attempt_at": "2023-02-01T00:00:00",
            "next_eligible_at": "",
        }
    )

    with pytest.raises(RuntimeError, match="boom"):
        orchestrator.run(tickers, start_date, end_date)

    final_state = orchestrator.load_state(start_date, end_date, tickers)
    assert final_state["run_status"] == "FAILED"
    assert final_state["completed_tickers"] == ["113052.SH"]
    assert final_state["pending_tickers"] == ["110088.SH"]
    assert final_state["failed_tickers"] == ["110088.SH"]
    assert final_state["last_processed_ticker"] == "113052.SH"
