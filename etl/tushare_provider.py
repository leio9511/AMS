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
    def fetch_cb_price_changes(self, ticker: str) -> pd.DataFrame:
        try:
            df = self.pro.cb_price_chg(ts_code=ticker)
            if df is not None and not df.empty:
                return df
            return pd.DataFrame()
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
