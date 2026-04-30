import pandas as pd
import tushare as ts
import logging
from etl.cb_provider_base import BaseDataProvider, DataProviderAuthError, DataProviderQuotaError, DataProviderError

logger = logging.getLogger(__name__)

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

            # Derive full stock ticker by appending the same suffix as the bond
            # In A-share market, convertible bonds and their underlying stocks trade on the same exchange.
            def get_full_stock_ticker(row):
                bond_code = row["code"]
                stock_code = row["company_code"]
                if pd.isna(bond_code) or pd.isna(stock_code):
                    return stock_code
                stock_code = str(stock_code).strip()
                if "." in stock_code:
                    return stock_code
                if "." in bond_code:
                    suffix = bond_code.split(".")[-1]
                    return f"{stock_code}.{suffix}"
                return stock_code
            
            df["company_code"] = df.apply(get_full_stock_ticker, axis=1)

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
        try:
            # 1. Get all trading days in the range using the existing trade calendar helper
            trade_days = self.fetch_trade_calendar(start_date, end_date)
            if not trade_days:
                return pd.DataFrame()

            all_frames = []
            # 2. fetch_cb_daily must query by trade_date (one date at a time) to retrieve the full-market CB daily snapshot.
            # Comma-separated ts_code batching is not supported by the cb_daily API and must not be used.
            for day in trade_days:
                ts_day = day.replace("-", "")
                df_day = self.pro.cb_daily(trade_date=ts_day)
                if df_day is not None and not df_day.empty:
                    all_frames.append(df_day)

            if not all_frames:
                return pd.DataFrame()

            df = pd.concat(all_frames)

            # 3. Rename columns to match pipeline contract
            df = df.rename(columns={"ts_code": "code", "trade_date": "time"})
            # Requirement 5: Align 'vol' to 'volume' for AMS canonical schema
            df = df.rename(columns={"vol": "volume"})

            # 4. Filter by requested tickers
            if tickers:
                df = df[df["code"].isin(tickers)]

            if df.empty:
                return pd.DataFrame()

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
        # cb_daily API does not provide a cb_over_rate field. premium_rate must be computed from bond_close, stock_close, and effective_conv_price.
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
            for ticker in tickers:
                # Many TuShare cb_* APIs expect a single ts_code. 
                # Loop explicitly to ensure reliable acquisition and avoid guessing batch support.
                df_chg = self.pro.cb_price_chg(ts_code=ticker)
                if df_chg is not None and not df_chg.empty:
                    all_chg.append(df_chg)
            df_chg = pd.concat(all_chg) if all_chg else pd.DataFrame(columns=["ts_code", "change_date", "convert_price_initial", "convertprice_aft"])
            
            # 3. Fetch underlying stock daily data
            underlying_stocks = list(set([self._bond_to_stock_map.get(t) for t in tickers if t in self._bond_to_stock_map]))
            df_stock_daily = pd.DataFrame()
            if underlying_stocks:
                stock_frames = []
                # pro.daily supports comma-separated ts_code batching up to 100+
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
                bond_chg = df_chg[df_chg["ts_code"] == ticker].copy() if not df_chg.empty else pd.DataFrame()
                stock_daily = df_stock_daily[df_stock_daily["stk_code"] == stk_code].copy() if (not df_stock_daily.empty and stk_code) else pd.DataFrame()
                
                # Sort for merge_asof
                bond_daily["time_dt"] = pd.to_datetime(bond_daily["time"])
                bond_daily = bond_daily.sort_values("time_dt")
                
                merged = bond_daily.copy()
                
                if not stock_daily.empty:
                    stock_daily["time_dt"] = pd.to_datetime(stock_daily["time"])
                    stock_daily = stock_daily.sort_values("time_dt")
                    
                    # Merge bond prices and stock prices
                    merged = pd.merge(
                        merged,
                        stock_daily[["time_dt", "close"]].rename(columns={"close": "stock_close"}),
                        on="time_dt",
                        how="left"
                    )
                else:
                    merged["stock_close"] = float("nan")
                
                # Rename bond close for exact formula match
                merged = merged.rename(columns={"close": "bond_close"})

                if not bond_chg.empty:
                    bond_chg["change_date_dt"] = pd.to_datetime(bond_chg["change_date"])
                    bond_chg = bond_chg.sort_values("change_date_dt")
                    
                    merged = pd.merge_asof(
                        merged,
                        bond_chg[["change_date_dt", "convertprice_aft"]].rename(columns={"convertprice_aft": "effective_conv_price"}),
                        left_on="time_dt",
                        right_on="change_date_dt",
                        direction="backward"
                    )
                    
                    # Fill initial price if before first change
                    # convert_price_initial in TuShare is the price before ANY change
                    initial_price = bond_chg["convert_price_initial"].iloc[0]
                    merged["effective_conv_price"] = merged["effective_conv_price"].fillna(initial_price)
                else:
                    merged["effective_conv_price"] = float("nan")

                # Reconstruct: premium_rate = (bond_close / ((100 / effective_conv_price) * stock_close) - 1) * 100
                # If stock_close or effective_conv_price is missing, result naturally becomes NaN.
                merged["convert_premium_rate"] = (
                    merged["bond_close"] / ((100 / merged["effective_conv_price"]) * merged["stock_close"]) - 1
                ) * 100
                
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
