import os
import json
import time

import socket
import datetime
import pandas as pd
from etl.cb_provider_base import DataProviderQuotaError
from etl.cb_field_registry import (
    TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC,
    TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL,
    TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST,
)

class TuShareEnrichmentOrchestrator:
    def __init__(self, provider, cache_dir="cache"):
        self.provider = provider
        self.cache_dir = cache_dir
        self.runs_dir = os.path.join(cache_dir, "tushare_premium_runs")
        self.chg_dir = os.path.join(cache_dir, "tushare_cb_price_chg")
        os.makedirs(self.runs_dir, exist_ok=True)
        os.makedirs(self.chg_dir, exist_ok=True)
        
    def _get_lock_path(self, start_date, end_date):
        return os.path.join(self.runs_dir, f"{start_date}_{end_date}.lock")
        
    def _get_state_path(self, start_date, end_date):
        return os.path.join(self.runs_dir, f"{start_date}_{end_date}.json")
        
    def acquire_lock(self, start_date, end_date):
        lock_path = self._get_lock_path(start_date, end_date)
        state_path = self._get_state_path(start_date, end_date)
        
        if os.path.exists(lock_path):
            with open(lock_path, "r") as f:
                try:
                    lock_data = json.load(f)
                except:
                    lock_data = {}
            
            pid = lock_data.get("owner_pid")
            created_at = lock_data.get("created_at")
            
            is_stale = False
            if pid:
                try:
                    os.kill(pid, 0)
                except OSError:
                    is_stale = True
            elif created_at:
                try:
                    created_dt = datetime.datetime.fromisoformat(created_at)
                    if (datetime.datetime.now() - created_dt).total_seconds() > 6 * 3600:
                        if os.path.exists(state_path):
                            mtime = os.path.getmtime(state_path)
                            if time.time() - mtime > 30 * 60:
                                is_stale = True
                        else:
                            is_stale = True
                except:
                    is_stale = True
            
            if not is_stale:
                raise RuntimeError("CONCURRENT_RUN_BLOCKED")
        
        lock_data = {
            "owner_pid": os.getpid(),
            "owner_hostname": socket.gethostname(),
            "created_at": datetime.datetime.now().isoformat(),
            "run_state_path": state_path
        }
        with open(lock_path, "w") as f:
            json.dump(lock_data, f)

    def release_lock(self, start_date, end_date):
        lock_path = self._get_lock_path(start_date, end_date)
        if os.path.exists(lock_path):
            os.remove(lock_path)
            
    def load_state(self, start_date, end_date, tickers):
        state_path = self._get_state_path(start_date, end_date)
        if os.path.exists(state_path):
            with open(state_path, "r") as f:
                state = json.load(f)
            return state
            
        return {
            "run_status": "PENDING",
            "provider": "tushare",
            "start_date": start_date,
            "end_date": end_date,
            "sorted_tickers": sorted(tickers),
            "completed_tickers": [],
            "pending_tickers": sorted(tickers),
            "failed_tickers": [],
            "last_processed_ticker": "",
            "sleep_seconds_between_calls": 15,
            "last_attempt_at": "",
            "next_eligible_at": ""
        }
        
    def save_state(self, state):
        state_path = self._get_state_path(state["start_date"], state["end_date"])
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def fetch_chg_with_cache(self, ticker):
        cache_path = os.path.join(self.chg_dir, f"{ticker}.json")
        if os.path.exists(cache_path):
            return pd.read_json(cache_path, orient="records")
            
        df = self.provider.fetch_cb_price_changes(ticker)
        if not df.empty:
            df.to_json(cache_path, orient="records")
        return df

    def run(self, tickers, start_date, end_date):
        self.acquire_lock(start_date, end_date)
        try:
            state = self.load_state(start_date, end_date, tickers)
            if state["run_status"] in ["COMPLETED"]:
                # Already complete, just reconstruct
                return self._reconstruct_premium(tickers, start_date, end_date)
                
            state["run_status"] = "RUNNING"
            self.save_state(state)
            
            rate_limited = False
            for ticker in list(state["pending_tickers"]):
                try:
                    state["last_attempt_at"] = datetime.datetime.now().isoformat()
                    self.fetch_chg_with_cache(ticker)
                    
                    state["completed_tickers"].append(ticker)
                    state["pending_tickers"].remove(ticker)
                    state["last_processed_ticker"] = ticker
                    self.save_state(state)
                    # Respect API limits loosely
                    time.sleep(0.1)
                except DataProviderQuotaError:
                    rate_limited = True
                    break
                except Exception:
                    state["failed_tickers"].append(ticker)
                    state["pending_tickers"].remove(ticker)
                    self.save_state(state)
                    
            if rate_limited:
                state["run_status"] = "RATE_LIMITED"
                self.save_state(state)
            elif state["failed_tickers"]:
                state["run_status"] = "PARTIAL_SUCCESS"
                self.save_state(state)
            else:
                state["run_status"] = "COMPLETED"
                self.save_state(state)
                
            df_result = self._reconstruct_premium(tickers, start_date, end_date)
            
            if rate_limited:
                raise DataProviderQuotaError("RATE_LIMITED")
                
            return df_result
            
        finally:
            self.release_lock(start_date, end_date)
            
    def _reconstruct_premium(self, tickers, start_date, end_date):
        ts_start = start_date.replace("-", "")
        ts_end = end_date.replace("-", "")
        
        if not hasattr(self.provider, '_bond_to_stock_map') or not self.provider._bond_to_stock_map:
            self.provider.fetch_cb_basic()
            
        df_basic = pd.DataFrame()
        try:
            df_basic = self.provider.fetch_cb_basic()
        except:
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
                    
        df_chg = pd.concat(all_chg) if all_chg else pd.DataFrame(columns=["ts_code", "change_date", "convert_price_initial", "convertprice_aft"])
        
        underlying_stocks = list(set([bond_to_stock.get(t) for t in tickers if t in bond_to_stock]))
        df_stock_daily = pd.DataFrame()
        if underlying_stocks:
            stock_frames = []
            for i in range(0, len(underlying_stocks), 100):
                batch = underlying_stocks[i:i+100]
                try:
                    df_s = self.provider.pro.daily(ts_code=",".join(batch), start_date=ts_start, end_date=ts_end)
                    if df_s is not None and not df_s.empty:
                        stock_frames.append(df_s)
                except:
                    pass
            if stock_frames:
                df_stock_daily = pd.concat(stock_frames)
                df_stock_daily = df_stock_daily.rename(columns={"ts_code": "stk_code", "trade_date": "time"})
                df_stock_daily["time"] = pd.to_datetime(df_stock_daily["time"]).dt.strftime("%Y-%m-%d")
        
        reconstructed_frames = []
        for ticker in tickers:
            bond_daily = df_bond_daily[df_bond_daily["code"] == ticker].copy()
            if bond_daily.empty:
                continue
            
            stk_code = bond_to_stock.get(ticker)
            bond_chg = df_chg[df_chg["ts_code"] == ticker].copy() if not df_chg.empty else pd.DataFrame()
            stock_daily = df_stock_daily[df_stock_daily["stk_code"] == stk_code].copy() if (not df_stock_daily.empty and stk_code) else pd.DataFrame()
            
            bond_daily["time_dt"] = pd.to_datetime(bond_daily["time"])
            bond_daily = bond_daily.sort_values("time_dt")
            
            merged = bond_daily.copy()
            
            if not stock_daily.empty:
                stock_daily["time_dt"] = pd.to_datetime(stock_daily["time"])
                stock_daily = stock_daily.sort_values("time_dt")
                merged = pd.merge(merged, stock_daily[["time_dt", "close"]].rename(columns={"close": "stock_close"}), on="time_dt", how="left")
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
                    bond_chg[["change_date_dt", "latest_non_null_convertprice_aft", "latest_available_convert_price_initial"]],
                    left_on="time_dt",
                    right_on="change_date_dt",
                    direction="backward"
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
                merged["effective_conv_price"] = pd.to_numeric(pd.Series(basic_conv.get(ticker, float("nan")), index=merged.index), errors="coerce")
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
