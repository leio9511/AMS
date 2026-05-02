import datetime
import json
import os
import socket
import time

import pandas as pd

from etl.cb_provider_base import DataProviderQuotaError
from etl.cb_field_registry import (
    TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC,
    TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL,
    TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST,
)


ALLOWED_RUN_STATUSES = {
    "PENDING",
    "RUNNING",
    "RATE_LIMITED",
    "PARTIAL_SUCCESS",
    "COMPLETED",
    "FAILED",
}

ALLOWED_RUN_TRANSITIONS = {
    ("PENDING", "RUNNING"),
    ("RUNNING", "COMPLETED"),
    ("RUNNING", "PARTIAL_SUCCESS"),
    ("RUNNING", "RATE_LIMITED"),
    ("RUNNING", "FAILED"),
    ("RATE_LIMITED", "RUNNING"),
    ("PARTIAL_SUCCESS", "RUNNING"),
}


class TuShareEnrichmentOrchestrator:
    stale_lock_after_seconds = 6 * 3600
    stale_state_after_seconds = 30 * 60

    def __init__(self, provider, cache_dir="cache", sleep_seconds_between_calls=0.1):
        self.provider = provider
        self.cache_dir = cache_dir
        self.sleep_seconds_between_calls = sleep_seconds_between_calls
        self.runs_dir = os.path.join(cache_dir, "tushare_premium_runs")
        self.chg_dir = os.path.join(cache_dir, "tushare_cb_price_chg")
        os.makedirs(self.runs_dir, exist_ok=True)
        os.makedirs(self.chg_dir, exist_ok=True)

    def _now(self):
        return datetime.datetime.now()

    def _get_lock_path(self, start_date, end_date):
        return os.path.join(self.runs_dir, f"{start_date}_{end_date}.lock")

    def _get_state_path(self, start_date, end_date):
        return os.path.join(self.runs_dir, f"{start_date}_{end_date}.json")

    def _parse_iso_datetime(self, value):
        if not value:
            return None
        try:
            return datetime.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    def _seconds_since(self, dt):
        if dt is None:
            return None
        now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else self._now()
        return (now - dt).total_seconds()

    def _pid_exists(self, pid):
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ValueError, TypeError):
            return False

    def _state_file_stale_or_missing(self, state_path):
        if not state_path or not os.path.exists(state_path):
            return True
        return time.time() - os.path.getmtime(state_path) > self.stale_state_after_seconds

    def _is_stale_lock(self, lock_data, default_state_path):
        pid = lock_data.get("owner_pid")
        if not self._pid_exists(pid):
            return True

        created_at = self._parse_iso_datetime(lock_data.get("created_at"))
        lock_age_seconds = self._seconds_since(created_at)
        state_path = lock_data.get("run_state_path") or default_state_path
        if lock_age_seconds is None:
            return True

        return (
            lock_age_seconds > self.stale_lock_after_seconds
            and self._state_file_stale_or_missing(state_path)
        )

    def acquire_lock(self, start_date, end_date):
        lock_path = self._get_lock_path(start_date, end_date)
        state_path = self._get_state_path(start_date, end_date)

        if os.path.exists(lock_path):
            with open(lock_path, "r") as f:
                try:
                    lock_data = json.load(f)
                except json.JSONDecodeError:
                    lock_data = {}

            if not self._is_stale_lock(lock_data, state_path):
                raise RuntimeError("CONCURRENT_RUN_BLOCKED")

        lock_data = {
            "owner_pid": os.getpid(),
            "owner_hostname": socket.gethostname(),
            "created_at": self._now().isoformat(),
            "run_state_path": state_path,
        }
        with open(lock_path, "w") as f:
            json.dump(lock_data, f, indent=2)

    def release_lock(self, start_date, end_date):
        lock_path = self._get_lock_path(start_date, end_date)
        if os.path.exists(lock_path):
            os.remove(lock_path)

    def _default_state(self, start_date, end_date, tickers):
        sorted_tickers = sorted(tickers)
        return {
            "run_status": "PENDING",
            "provider": "tushare",
            "start_date": start_date,
            "end_date": end_date,
            "sorted_tickers": sorted_tickers,
            "completed_tickers": [],
            "pending_tickers": sorted_tickers.copy(),
            "failed_tickers": [],
            "last_processed_ticker": "",
            "sleep_seconds_between_calls": self.sleep_seconds_between_calls,
            "last_attempt_at": "",
            "next_eligible_at": "",
        }

    def _normalize_state(self, state, start_date, end_date, tickers):
        defaults = self._default_state(start_date, end_date, tickers)
        normalized = {**defaults, **(state or {})}

        if normalized["run_status"] not in ALLOWED_RUN_STATUSES:
            raise RuntimeError(f"Invalid TuShare enrichment run_status: {normalized['run_status']}")

        normalized["provider"] = "tushare"
        normalized["start_date"] = start_date
        normalized["end_date"] = end_date
        normalized["sorted_tickers"] = sorted(normalized.get("sorted_tickers") or sorted(tickers))

        for key in ["completed_tickers", "pending_tickers", "failed_tickers"]:
            values = normalized.get(key) or []
            normalized[key] = list(dict.fromkeys(values))

        completed = set(normalized["completed_tickers"])
        failed = set(normalized["failed_tickers"])
        if not normalized["pending_tickers"] and normalized["run_status"] not in {"COMPLETED", "FAILED"}:
            normalized["pending_tickers"] = [
                ticker for ticker in normalized["sorted_tickers"] if ticker not in completed and ticker not in failed
            ]

        normalized["sleep_seconds_between_calls"] = self.sleep_seconds_between_calls
        normalized.setdefault("last_attempt_at", "")
        normalized.setdefault("next_eligible_at", "")
        normalized.setdefault("last_processed_ticker", "")
        return normalized

    def load_state(self, start_date, end_date, tickers):
        state_path = self._get_state_path(start_date, end_date)
        if os.path.exists(state_path):
            with open(state_path, "r") as f:
                state = json.load(f)
            return self._normalize_state(state, start_date, end_date, tickers)

        return self._default_state(start_date, end_date, tickers)

    def save_state(self, state):
        state = self._normalize_state(
            state,
            state["start_date"],
            state["end_date"],
            state.get("sorted_tickers") or state.get("pending_tickers") or [],
        )
        state_path = self._get_state_path(state["start_date"], state["end_date"])
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _transition_state(self, state, new_status):
        old_status = state.get("run_status")
        if new_status not in ALLOWED_RUN_STATUSES:
            raise RuntimeError(f"Invalid TuShare enrichment run_status: {new_status}")
        if old_status != new_status and (old_status, new_status) not in ALLOWED_RUN_TRANSITIONS:
            raise RuntimeError(f"Invalid TuShare enrichment state transition: {old_status} -> {new_status}")
        state["run_status"] = new_status
        self.save_state(state)

    def _record_attempt_metadata(self, state, attempted_at=None):
        attempted_at = attempted_at or self._now()
        state["last_attempt_at"] = attempted_at.isoformat()
        state["sleep_seconds_between_calls"] = self.sleep_seconds_between_calls
        self.save_state(state)
        return attempted_at

    def _record_next_eligible_at(self, state, attempted_at):
        next_eligible_at = attempted_at + datetime.timedelta(seconds=self.sleep_seconds_between_calls)
        state["next_eligible_at"] = next_eligible_at.isoformat()

    def fetch_chg_with_cache(self, ticker):
        cache_path = os.path.join(self.chg_dir, f"{ticker}.json")
        if os.path.exists(cache_path):
            return pd.read_json(cache_path, orient="records")

        df = self.provider.fetch_cb_price_changes(ticker)
        if df is not None and not df.empty:
            df.to_json(cache_path, orient="records")
        return df if df is not None else pd.DataFrame()

    def run(self, tickers, start_date, end_date):
        self.acquire_lock(start_date, end_date)
        try:
            state = self.load_state(start_date, end_date, tickers)
            if state["run_status"] == "COMPLETED":
                return self._reconstruct_premium(tickers, start_date, end_date)
            if state["run_status"] == "FAILED":
                raise RuntimeError("TuShare enrichment run is already in FAILED terminal state")

            self._transition_state(state, "RUNNING")

            for ticker in list(state["pending_tickers"]):
                attempted_at = self._record_attempt_metadata(state)
                try:
                    self.fetch_chg_with_cache(ticker)
                except DataProviderQuotaError:
                    self._record_next_eligible_at(state, attempted_at)
                    self._transition_state(state, "RATE_LIMITED")
                    raise DataProviderQuotaError("RATE_LIMITED")
                except Exception as exc:
                    if ticker not in state["failed_tickers"]:
                        state["failed_tickers"].append(ticker)
                    self._transition_state(state, "FAILED")
                    raise RuntimeError(str(exc)) from exc

                if ticker not in state["completed_tickers"]:
                    state["completed_tickers"].append(ticker)
                if ticker in state["pending_tickers"]:
                    state["pending_tickers"].remove(ticker)
                state["last_processed_ticker"] = ticker
                state["next_eligible_at"] = ""
                self.save_state(state)

                if state["pending_tickers"]:
                    time.sleep(self.sleep_seconds_between_calls)

            try:
                df_result = self._reconstruct_premium(tickers, start_date, end_date)
            except Exception as exc:
                self._transition_state(state, "FAILED")
                raise RuntimeError(str(exc)) from exc

            if state["failed_tickers"]:
                self._transition_state(state, "PARTIAL_SUCCESS")
            else:
                self._transition_state(state, "COMPLETED")

            return df_result

        finally:
            self.release_lock(start_date, end_date)

    def _reconstruct_premium(self, tickers, start_date, end_date):
        ts_start = start_date.replace("-", "")
        ts_end = end_date.replace("-", "")

        if not hasattr(self.provider, "_bond_to_stock_map") or not self.provider._bond_to_stock_map:
            self.provider.fetch_cb_basic()

        df_basic = pd.DataFrame()
        try:
            df_basic = self.provider.fetch_cb_basic()
        except Exception:
            pass

        bond_to_stock = self.provider._bond_to_stock_map
        basic_conv = {}
        if not df_basic.empty and "conv_price" in df_basic.columns and "code" in df_basic.columns:
            basic_conv = df_basic.set_index("code")["conv_price"].to_dict()

        df_bond_daily = self.provider.fetch_cb_daily(tickers, start_date, end_date)
        if df_bond_daily.empty:
            return pd.DataFrame()
        df_bond_daily = df_bond_daily.reset_index()

        all_chg = []
        for ticker in tickers:
            cache_path = os.path.join(self.chg_dir, f"{ticker}.json")
            if os.path.exists(cache_path):
                try:
                    df_chg = pd.read_json(cache_path, orient="records")
                    if not df_chg.empty:
                        df_chg["ts_code"] = ticker
                        all_chg.append(df_chg)
                except Exception:
                    pass

        df_chg = (
            pd.concat(all_chg)
            if all_chg
            else pd.DataFrame(columns=["ts_code", "change_date", "convert_price_initial", "convertprice_aft"])
        )

        underlying_stocks = list(set([bond_to_stock.get(t) for t in tickers if t in bond_to_stock]))
        df_stock_daily = pd.DataFrame()
        if underlying_stocks:
            df_stock_daily = self.provider.fetch_stock_daily(underlying_stocks, start_date, end_date)
            if df_stock_daily is None:
                df_stock_daily = pd.DataFrame()
            elif not df_stock_daily.empty:
                df_stock_daily = df_stock_daily.copy()
                if "ts_code" in df_stock_daily.columns and "stk_code" not in df_stock_daily.columns:
                    df_stock_daily = df_stock_daily.rename(columns={"ts_code": "stk_code"})
                if "trade_date" in df_stock_daily.columns and "time" not in df_stock_daily.columns:
                    df_stock_daily = df_stock_daily.rename(columns={"trade_date": "time"})
                if "time" in df_stock_daily.columns:
                    df_stock_daily["time"] = pd.to_datetime(df_stock_daily["time"]).dt.strftime("%Y-%m-%d")

        reconstructed_frames = []
        for ticker in tickers:
            bond_daily = df_bond_daily[df_bond_daily["code"] == ticker].copy()
            if bond_daily.empty:
                continue

            stk_code = bond_to_stock.get(ticker)
            bond_chg = df_chg[df_chg["ts_code"] == ticker].copy() if not df_chg.empty else pd.DataFrame()
            stock_daily = (
                df_stock_daily[df_stock_daily["stk_code"] == stk_code].copy()
                if (not df_stock_daily.empty and stk_code)
                else pd.DataFrame()
            )

            bond_daily["time_dt"] = pd.to_datetime(bond_daily["time"])
            bond_daily = bond_daily.sort_values("time_dt")

            merged = bond_daily.copy()

            if not stock_daily.empty:
                stock_daily["time_dt"] = pd.to_datetime(stock_daily["time"])
                stock_daily = stock_daily.sort_values("time_dt")
                merged = pd.merge(
                    merged,
                    stock_daily[["time_dt", "close"]].rename(columns={"close": "stock_close"}),
                    on="time_dt",
                    how="left",
                )
            else:
                merged["stock_close"] = float("nan")

            merged = merged.rename(columns={"close": "bond_close"})

            if not bond_chg.empty:
                bond_chg["change_date_dt"] = pd.to_datetime(bond_chg["change_date"])
                bond_chg = bond_chg.sort_values("change_date_dt")

                if "convertprice_aft" not in bond_chg.columns:
                    bond_chg["convertprice_aft"] = float("nan")
                if "convert_price_initial" not in bond_chg.columns:
                    bond_chg["convert_price_initial"] = float("nan")

                bond_chg["latest_non_null_convertprice_aft"] = pd.to_numeric(
                    bond_chg["convertprice_aft"], errors="coerce"
                ).ffill()
                bond_chg["latest_available_convert_price_initial"] = pd.to_numeric(
                    bond_chg["convert_price_initial"], errors="coerce"
                ).ffill()

                merged = pd.merge_asof(
                    merged,
                    bond_chg[
                        [
                            "change_date_dt",
                            "latest_non_null_convertprice_aft",
                            "latest_available_convert_price_initial",
                        ]
                    ],
                    left_on="time_dt",
                    right_on="change_date_dt",
                    direction="backward",
                )

                if "latest_non_null_convertprice_aft" not in merged.columns:
                    merged["latest_non_null_convertprice_aft"] = float("nan")
                if "latest_available_convert_price_initial" not in merged.columns:
                    merged["latest_available_convert_price_initial"] = float("nan")

                latest_aft = pd.to_numeric(merged["latest_non_null_convertprice_aft"], errors="coerce")
                initial = pd.to_numeric(merged["latest_available_convert_price_initial"], errors="coerce")
                basic = pd.Series(basic_conv.get(ticker, float("nan")), index=merged.index)
                basic = pd.to_numeric(basic, errors="coerce")

                merged["effective_conv_price"] = latest_aft
                merged["convert_price_provenance"] = pd.NA
                aft_mask = latest_aft.notna()
                merged.loc[aft_mask, "convert_price_provenance"] = TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST

                use_initial = merged["effective_conv_price"].isna() & initial.notna()
                merged.loc[use_initial, "effective_conv_price"] = initial.loc[use_initial]
                merged.loc[use_initial, "convert_price_provenance"] = TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL

                use_basic = merged["effective_conv_price"].isna() & basic.notna()
                merged.loc[use_basic, "effective_conv_price"] = basic.loc[use_basic]
                merged.loc[use_basic, "convert_price_provenance"] = TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC
                merged.loc[merged["effective_conv_price"].isna(), "convert_price_provenance"] = pd.NA
            else:
                merged["effective_conv_price"] = pd.to_numeric(
                    pd.Series(basic_conv.get(ticker, float("nan")), index=merged.index), errors="coerce"
                )
                merged["convert_price_provenance"] = pd.NA
                basic_mask = merged["effective_conv_price"].notna()
                merged.loc[basic_mask, "convert_price_provenance"] = TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC

            merged["convert_price"] = merged["effective_conv_price"]

            merged["convert_premium_rate"] = (
                merged["bond_close"] / ((100 / merged["effective_conv_price"]) * merged["stock_close"]) - 1
            ) * 100

            reconstructed_frames.append(merged.rename(columns={"time": "date"}))

        if not reconstructed_frames:
            return pd.DataFrame()

        df_result = pd.concat(reconstructed_frames)
        return df_result[["code", "date", "convert_price", "convert_price_provenance", "convert_premium_rate"]]
