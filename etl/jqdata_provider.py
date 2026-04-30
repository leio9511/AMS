import pandas as pd
import jqdatasdk
from etl.cb_provider_base import BaseDataProvider, DataProviderAuthError, DataProviderQuotaError, DataProviderError

class JQDataProvider(BaseDataProvider):
    def __init__(self, jqdata_client=None):
        self.client = jqdata_client if jqdata_client is not None else jqdatasdk

    def _handle_exception(self, e):
        err_msg = str(e).lower()
        if "auth" in err_msg or "login" in err_msg or "password" in err_msg:
            raise DataProviderAuthError(f"JQData auth failure: {e}")
        if "quota" in err_msg or "limit" in err_msg:
            raise DataProviderQuotaError(f"JQData quota exceeded: {e}")
        raise DataProviderError(f"JQData error: {e}")

    def fetch_cb_basic(self) -> pd.DataFrame:
        try:
            q = self.client.query(self.client.bond.CONBOND_BASIC_INFO)
            return self.client.bond.run_query(q)
        except Exception as e:
            self._handle_exception(e)

    def fetch_cb_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        try:
            df = self.client.get_price(
                tickers,
                start_date=start_date,
                end_date=end_date,
                frequency="daily",
                fields=["open", "high", "low", "close", "volume"],
            )
            return df
        except Exception as e:
            self._handle_exception(e)

    def fetch_cb_price_changes(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Implementation of premium/valuation data acquisition for JQData.
        Note: This corresponds to CONBOND_DAILY_CONVERT in JQData.
        """
        if not tickers:
            return pd.DataFrame()
            
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        all_frames = []
        current_start = start_dt
        try:
            while current_start <= end_dt:
                current_end = (current_start + pd.offsets.MonthEnd(0))
                if current_end > end_dt:
                    current_end = end_dt
                
                s_date = current_start.strftime("%Y-%m-%d")
                e_date = current_end.strftime("%Y-%m-%d")
                
                code_batch_size = 100
                for i in range(0, len(tickers), code_batch_size):
                    batch_codes = tickers[i:i + code_batch_size]
                    # Strip suffixes for JQData CONBOND_DAILY_CONVERT query which expects raw codes
                    raw_batch_codes = [c.split('.')[0] for c in batch_codes]
                    q = self.client.query(self.client.bond.CONBOND_DAILY_CONVERT).filter(
                        self.client.bond.CONBOND_DAILY_CONVERT.code.in_(raw_batch_codes),
                        self.client.bond.CONBOND_DAILY_CONVERT.date >= s_date,
                        self.client.bond.CONBOND_DAILY_CONVERT.date <= e_date,
                    )
                    df_batch = self.client.bond.run_query(q)
                    
                    if len(df_batch) == 5000:
                        raise DataProviderError("Premium source query returned the provider single-call cap characteristic and must be retried with deterministic batching.")
                    
                    all_frames.append(df_batch)
                
                current_start = current_end + pd.Timedelta(days=1)
                
            if not all_frames:
                return pd.DataFrame()
                
            return pd.concat(all_frames)
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise e
            self._handle_exception(e)

    def fetch_stock_st_by_date(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        try:
            df = self.client.get_extras("is_st", tickers, start_date=start_date, end_date=end_date)
            return df
        except Exception as e:
            # Classification as per pipeline logic
            err_msg = str(e).lower()
            if any(kw in err_msg for kw in ["window", "range", "permission", "account", "support"]):
                 # We can wrap this in a more specific error if needed, but for now DataProviderError is fine
                 pass
            self._handle_exception(e)

    def fetch_trade_calendar(self, start_date: str, end_date: str) -> list:
        try:
            return self.client.get_trade_days(start_date=start_date, end_date=end_date).tolist()
        except Exception as e:
            self._handle_exception(e)

    def fetch_all_securities(self, types: list[str] = ["conbond"]) -> pd.DataFrame:
        try:
            return self.client.get_all_securities(types)
        except Exception as e:
            self._handle_exception(e)
