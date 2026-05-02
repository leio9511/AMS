import pandas as pd
import jqdatasdk
from etl.cb_provider_base import BaseDataProvider, DataProviderAuthError, DataProviderQuotaError, DataProviderError
from etl.cb_audit_contract import JQDATA_CONVERT_PRICE_PROVENANCE

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

        raw_code_to_exchange: dict[str, str] = {}
        for ticker in tickers:
            ticker_str = str(ticker).strip()
            if not ticker_str:
                continue
            parts = ticker_str.split(".", 1)
            raw_code = parts[0].strip()
            exchange_code = parts[1].strip() if len(parts) > 1 else ""
            if not raw_code or not exchange_code:
                continue

            existing_exchange = raw_code_to_exchange.get(raw_code)
            if existing_exchange is not None and existing_exchange != exchange_code:
                raise DataProviderError(
                    f"Conflicting JQData premium exchange suffixes for raw bond code {raw_code}: "
                    f"{existing_exchange} vs {exchange_code}"
                )
            raw_code_to_exchange[raw_code] = exchange_code
            
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
                    raw_batch_codes = [str(c).split('.')[0].strip() for c in batch_codes]
                    q = self.client.query(
                        self.client.bond.CONBOND_DAILY_CONVERT.code,
                        self.client.bond.CONBOND_DAILY_CONVERT.date,
                        self.client.bond.CONBOND_DAILY_CONVERT.convert_price,
                        self.client.bond.CONBOND_DAILY_CONVERT.convert_premium_rate
                    ).filter(
                        self.client.bond.CONBOND_DAILY_CONVERT.code.in_(raw_batch_codes),
                        self.client.bond.CONBOND_DAILY_CONVERT.date >= s_date,
                        self.client.bond.CONBOND_DAILY_CONVERT.date <= e_date,
                    )
                    df_batch = self.client.bond.run_query(q)
                    if df_batch is not None and not df_batch.empty:
                        df_batch = df_batch.copy()
                        if "code" in df_batch.columns and raw_code_to_exchange:
                            response_raw_codes = df_batch["code"].astype(str).str.split(".", n=1).str[0].str.strip()
                            restored_exchange = response_raw_codes.map(raw_code_to_exchange)
                            if "exchange_code" not in df_batch.columns:
                                df_batch["exchange_code"] = restored_exchange
                            else:
                                exchange_as_text = df_batch["exchange_code"].astype("string")
                                missing_exchange = (
                                    df_batch["exchange_code"].isna()
                                    | exchange_as_text.str.strip().fillna("").eq("")
                                    | exchange_as_text.str.strip().str.lower().fillna("").isin(["nan", "none", "nat"])
                                )
                                df_batch.loc[missing_exchange & restored_exchange.notna(), "exchange_code"] = restored_exchange

                        if "convert_price" in df_batch.columns:
                            if "convert_price_provenance" not in df_batch.columns:
                                df_batch["convert_price_provenance"] = pd.NA
                            has_convert_price = df_batch["convert_price"].notna()
                            df_batch.loc[has_convert_price, "convert_price_provenance"] = JQDATA_CONVERT_PRICE_PROVENANCE
                    
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

    def fetch_stock_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_stock_st_by_date(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        try:
            df = self.client.get_extras("is_st", tickers, start_date=start_date, end_date=end_date)
            return df
        except Exception as e:
            err_msg = str(e).lower()
            if any(kw in err_msg for kw in ["window", "range", "permission", "account", "support"]):
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
