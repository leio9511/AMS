import pandas as pd
import tushare as ts
import logging
from etl.cb_provider_base import BaseDataProvider, DataProviderAuthError, DataProviderQuotaError, DataProviderError

logger = logging.getLogger(__name__)

TUSHARE_PREMIUM_GUARD_MESSAGE = "TuShare premium_rate must be derived from trade-date-correct effective conversion prices and must not be computed from a single static latest conversion price."

class TuShareProvider(BaseDataProvider):
    def __init__(self, token=None, pro=None):
        if pro is not None:
            self.pro = pro
        else:
            if token:
                ts.set_token(token)
            self.pro = ts.pro_api()
        self._bond_to_stock_map = {}

    def _handle_exception(self, e):
        err_msg = str(e).lower()
        if "token" in err_msg or "认证" in err_msg or "401" in err_msg:
            raise DataProviderAuthError(f"TuShare auth failure: {e}")
        if "次数" in err_msg or "频率" in err_msg or "limit" in err_msg or "每分钟" in err_msg or "403" in err_msg:
            raise DataProviderQuotaError(f"TuShare quota exceeded: {e}")
        raise DataProviderError(f"TuShare error: {e}")

    def fetch_cb_basic(self) -> pd.DataFrame:
        try:
            df = self.pro.cb_basic()
            # Map columns to match what CBETLPipeline expects: code, company_code, delist_Date
            mapping = {
                "ts_code": "code",
                "stk_code": "company_code",
                "delist_date": "delist_Date"
            }
            df = df.rename(columns=mapping)
            # Cache bond to stock mapping for reconstruction
            for _, row in df.iterrows():
                if pd.notna(row["code"]) and pd.notna(row["company_code"]):
                    self._bond_to_stock_map[row["code"]] = row["company_code"]
            return df
        except Exception as e:
            self._handle_exception(e)

    def fetch_all_securities(self, types: list[str] = ["conbond"]) -> pd.DataFrame:
        try:
            if "conbond" in types:
                df = self.pro.cb_basic()
                if df.empty:
                    return pd.DataFrame()
                df = df.set_index("ts_code")
                return df
            return pd.DataFrame()
        except Exception as e:
            self._handle_exception(e)

    def fetch_cb_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        ts_start = start_date.replace("-", "")
        ts_end = end_date.replace("-", "")
        
        all_frames = []
        try:
            # Batch by ticker to avoid URL length limits
            batch_size = 100
            for i in range(0, len(tickers), batch_size):
                batch = tickers[i:i+batch_size]
                ts_codes = ",".join(batch)
                df = self.pro.cb_daily(ts_code=ts_codes, start_date=ts_start, end_date=ts_end)
                all_frames.append(df)
            
            if not all_frames:
                return pd.DataFrame()
            
            df = pd.concat(all_frames)
            df = df.rename(columns={"ts_code": "code", "trade_date": "time"})
            # Convert time to YYYY-MM-DD for pipeline consistency
            df["time"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d")
            return df.set_index(["code", "time"])
        except Exception as e:
            self._handle_exception(e)

    def fetch_cb_price_changes(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Implementation of premium/valuation data acquisition for TuShare.
        Reconstructs 'premium_rate' using historical conversion prices and stock prices.
        """
        try:
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            
            # 0. Ensure bond to stock mapping is available
            if not self._bond_to_stock_map:
                self.fetch_cb_basic()
            
            # 1. Fetch bond daily data for prices
            df_bond_daily = self.fetch_cb_daily(tickers, start_date, end_date)
            if df_bond_daily.empty:
                return pd.DataFrame()
            df_bond_daily = df_bond_daily.reset_index()
            
            # 2. Fetch conversion price changes
            all_chg = []
            for i in range(0, len(tickers), 100):
                batch = tickers[i:i+100]
                df_chg = self.pro.cb_price_chg(ts_code=",".join(batch))
                if df_chg is not None and not df_chg.empty:
                    all_chg.append(df_chg)
            df_chg = pd.concat(all_chg) if all_chg else pd.DataFrame(columns=["ts_code", "change_date", "convert_price_initial", "convertprice_aft"])
            
            # 3. Fetch underlying stock daily data
            underlying_stocks = list(set([self._bond_to_stock_map.get(t) for t in tickers if t in self._bond_to_stock_map]))
            df_stock_daily = pd.DataFrame()
            if underlying_stocks:
                stock_frames = []
                for i in range(0, len(underlying_stocks), 100):
                    batch = underlying_stocks[i:i+100]
                    df_s = self.pro.daily(ts_code=",".join(batch), start_date=ts_start, end_date=ts_end)
                    if df_s is not None and not df_s.empty:
                        stock_frames.append(df_s)
                if stock_frames:
                    df_stock_daily = pd.concat(stock_frames)
                    df_stock_daily = df_stock_daily.rename(columns={"ts_code": "stk_code", "trade_date": "time"})
                    df_stock_daily["time"] = pd.to_datetime(df_stock_daily["time"]).dt.strftime("%Y-%m-%d")
            
            # 4. Reconstruct premium_rate
            reconstructed_frames = []
            for ticker in tickers:
                bond_daily = df_bond_daily[df_bond_daily["code"] == ticker].copy()
                if bond_daily.empty:
                    continue
                
                stk_code = self._bond_to_stock_map.get(ticker)
                if not stk_code or df_stock_daily.empty:
                    logger.warning(f"{ticker}: {TUSHARE_PREMIUM_GUARD_MESSAGE} (Missing stock mapping or prices, using reported cb_over_rate)")
                    bond_daily["convert_premium_rate"] = bond_daily["cb_over_rate"]
                    reconstructed_frames.append(bond_daily.rename(columns={"time": "date"}))
                    continue

                bond_chg = df_chg[df_chg["ts_code"] == ticker].copy() if not df_chg.empty else pd.DataFrame()
                stock_daily = df_stock_daily[df_stock_daily["stk_code"] == stk_code].copy()
                
                # Sort for merge_asof
                bond_daily["time_dt"] = pd.to_datetime(bond_daily["time"])
                stock_daily["time_dt"] = pd.to_datetime(stock_daily["time"])
                
                bond_daily = bond_daily.sort_values("time_dt")
                stock_daily = stock_daily.sort_values("time_dt")
                
                # Merge bond prices and stock prices
                merged = pd.merge(
                    bond_daily,
                    stock_daily[["time_dt", "close"]].rename(columns={"close": "stock_price"}),
                    on="time_dt",
                    how="left"
                )
                
                if not bond_chg.empty:
                    bond_chg["change_date_dt"] = pd.to_datetime(bond_chg["change_date"])
                    bond_chg = bond_chg.sort_values("change_date_dt")
                    
                    merged = pd.merge_asof(
                        merged,
                        bond_chg[["change_date_dt", "convertprice_aft"]],
                        left_on="time_dt",
                        right_on="change_date_dt",
                        direction="backward"
                    )
                    
                    # Fill initial price if before first change
                    initial_price = bond_chg["convert_price_initial"].iloc[0]
                    merged["convertprice_aft"] = merged["convertprice_aft"].fillna(initial_price)
                else:
                    # If no history, we can't reliably reconstruct, use reported
                    logger.warning(f"{ticker}: {TUSHARE_PREMIUM_GUARD_MESSAGE} (No conversion price history, using reported cb_over_rate)")
                    merged["convert_premium_rate"] = merged["cb_over_rate"]
                    reconstructed_frames.append(merged.rename(columns={"time": "date"}))
                    continue

                # Reconstruct: premium_rate = (bond_price / ((100 / effective_conv_price) * stock_price) - 1) * 100
                # Using 'close' from bond_daily (merged)
                merged["convert_premium_rate"] = (
                    merged["close"] / ((100 / merged["convertprice_aft"]) * merged["stock_price"]) - 1
                ) * 100
                
                # Fallback for missing stock prices or conv prices
                merged["convert_premium_rate"] = merged["convert_premium_rate"].fillna(merged["cb_over_rate"])
                
                reconstructed_frames.append(merged.rename(columns={"time": "date"}))
            
            if not reconstructed_frames:
                return pd.DataFrame()
            
            df_result = pd.concat(reconstructed_frames)
            return df_result[["code", "date", "convert_premium_rate"]]
            
        except Exception as e:
            self._handle_exception(e)

    def fetch_stock_st_by_date(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Optimized ST status fetching: Queries by trade_date for the range to avoid 
        per-ticker API calls which are slow and hit rate limits.
        """
        try:
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            
            # 1. Get trade days in range
            cal_df = self.pro.trade_cal(exchange='SSE', start_date=ts_start, end_date=ts_end, is_open='1')
            if cal_df.empty:
                return pd.DataFrame(index=[], columns=tickers)
            
            trade_days_ts = cal_df["cal_date"].tolist()
            trade_days_fmt = pd.to_datetime(cal_df["cal_date"]).dt.strftime("%Y-%m-%d").tolist()
            
            result_df = pd.DataFrame(index=trade_days_fmt, columns=tickers, data=False)
            ticker_set = set(tickers)
            
            # 2. Query stock_st for each trade day (much faster for large universes)
            for t_ts, t_fmt in zip(trade_days_ts, trade_days_fmt):
                df_st = self.pro.stock_st(trade_date=t_ts)
                if df_st is not None and not df_st.empty:
                    # Filter for tickers of interest that are in the ST list
                    st_on_day = df_st[df_st["ts_code"].isin(ticker_set)]["ts_code"].tolist()
                    for ticker in st_on_day:
                        result_df.at[t_fmt, ticker] = True
            
            return result_df
        except Exception as e:
            self._handle_exception(e)

    def fetch_trade_calendar(self, start_date: str, end_date: str) -> list:
        try:
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            df = self.pro.trade_cal(exchange='SSE', start_date=ts_start, end_date=ts_end, is_open='1')
            return pd.to_datetime(df["cal_date"]).dt.strftime("%Y-%m-%d").tolist()
        except Exception as e:
            self._handle_exception(e)
