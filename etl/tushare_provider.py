import logging
from dataclasses import dataclass

import pandas as pd
import tushare as ts

from etl.cb_provider_base import (
    BaseDataProvider,
    DataProviderAuthError,
    DataProviderError,
    DataProviderQuotaError,
)

logger = logging.getLogger(__name__)

IMPORT_COLUMNS = [
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "source",
    "updated_at",
]
SOURCE_TUSHARE = "tushare"
CALL_TYPE_REDEEM = "强赎"


@dataclass
class MappedRedemptionResult:
    df: pd.DataFrame
    filtered_snapshot_ids: list[str]
    rejected_duplicates: list[dict]


class TuShareProvider(BaseDataProvider):
    def __init__(self, token=None, pro=None):
        if pro is not None:
            self.pro = pro
        else:
            if token:
                ts.set_token(token)
            self.pro = ts.pro_api()
        self._bond_to_stock_map = {}

    @staticmethod
    def _normalize_tushare_date(value) -> str:
        if pd.isna(value):
            return ""

        raw = str(value).strip()
        if not raw or raw.lower() == "nat":
            return ""

        try:
            return pd.to_datetime(raw).strftime("%Y-%m-%d")
        except Exception:
            if len(raw) == 8 and raw.isdigit():
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
            return raw

    @staticmethod
    def _source_id_date_token(value) -> str:
        if pd.isna(value):
            return ""

        raw = str(value).strip()
        if not raw:
            return ""
        if raw.endswith(".0") and raw[:-2].isdigit():
            return raw[:-2]
        if len(raw) == 8 and raw.isdigit():
            return raw

        normalized = TuShareProvider._normalize_tushare_date(raw)
        if normalized:
            return normalized.replace("-", "")
        return raw

    @staticmethod
    def _json_safe_scalar(value):
        if value is None:
            return None

        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            try:
                value = value.item()
            except Exception:
                pass

        if pd.isna(value):
            return ""

        if isinstance(value, pd.Timestamp):
            return value.isoformat()

        if isinstance(value, (str, int, float, bool)):
            return value

        return str(value)

    @classmethod
    def _json_safe_records(cls, df: pd.DataFrame) -> list[dict]:
        records = []
        for record in df.to_dict(orient="records"):
            records.append({key: cls._json_safe_scalar(value) for key, value in record.items()})
        return records

    @staticmethod
    def _empty_mapped_redemption_result() -> MappedRedemptionResult:
        return MappedRedemptionResult(
            df=pd.DataFrame(columns=IMPORT_COLUMNS),
            filtered_snapshot_ids=[],
            rejected_duplicates=[],
        )

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
                "delist_date": "delist_Date",
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

    def fetch_and_map_redemption_events(self, start_date: str, end_date: str) -> MappedRedemptionResult:
        try:
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            cb_call_df = self.pro.cb_call(start_date=ts_start, end_date=ts_end)

            if cb_call_df is None or cb_call_df.empty:
                return self._empty_mapped_redemption_result()

            filtered_raw_df = cb_call_df.copy()
            if "call_type" not in filtered_raw_df.columns:
                return self._empty_mapped_redemption_result()

            filtered_raw_df = filtered_raw_df[filtered_raw_df["call_type"] == CALL_TYPE_REDEEM].copy()
            if filtered_raw_df.empty:
                return self._empty_mapped_redemption_result()

            filtered_raw_df = filtered_raw_df.fillna("")
            identity_df = filtered_raw_df.copy()
            identity_df["source_native_event_id"] = identity_df.apply(
                lambda row: (
                    f"{str(row.get('ts_code', '')).strip().replace('.', '')}_"
                    f"{self._source_id_date_token(row.get('ann_date', ''))}"
                ),
                axis=1,
            )
            filtered_snapshot_ids = identity_df["source_native_event_id"].astype(str).tolist()

            duplicate_mask = identity_df["source_native_event_id"].duplicated(keep=False)
            rejected_duplicates = []
            if duplicate_mask.any():
                rejected_duplicates = self._json_safe_records(filtered_raw_df.loc[duplicate_mask].copy())
                identity_df = identity_df.loc[~duplicate_mask].copy()

            if identity_df.empty:
                return MappedRedemptionResult(
                    df=pd.DataFrame(columns=IMPORT_COLUMNS),
                    filtered_snapshot_ids=filtered_snapshot_ids,
                    rejected_duplicates=rejected_duplicates,
                )

            cb_basic_df = self.fetch_cb_basic()
            if cb_basic_df is None or cb_basic_df.empty:
                cb_basic_df = pd.DataFrame(columns=["code", "delist_Date"])
            else:
                cb_basic_df = cb_basic_df.copy()
                if "code" not in cb_basic_df.columns and "ts_code" in cb_basic_df.columns:
                    cb_basic_df = cb_basic_df.rename(columns={"ts_code": "code"})
                if "delist_Date" not in cb_basic_df.columns and "delist_date" in cb_basic_df.columns:
                    cb_basic_df = cb_basic_df.rename(columns={"delist_date": "delist_Date"})
                for required_column in ["code", "delist_Date"]:
                    if required_column not in cb_basic_df.columns:
                        cb_basic_df[required_column] = ""
                cb_basic_df = cb_basic_df[["code", "delist_Date"]]

            merged_df = identity_df.merge(
                cb_basic_df,
                how="left",
                left_on="ts_code",
                right_on="code",
            )
            merged_df = merged_df.fillna("")

            updated_at = pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
            mapped_df = pd.DataFrame(
                {
                    "source_native_event_id": merged_df["source_native_event_id"].astype(str),
                    "bond_code": merged_df["ts_code"].astype(str).str.split(".").str[0],
                    "announcement_date": merged_df["ann_date"].apply(self._normalize_tushare_date),
                    "delisting_date": merged_df.apply(
                        lambda row: self._normalize_tushare_date(
                            row.get("delist_Date") or row.get("call_date") or ""
                        ),
                        axis=1,
                    ),
                    "source": SOURCE_TUSHARE,
                    "updated_at": updated_at,
                }
            )
            mapped_df = mapped_df[IMPORT_COLUMNS].fillna("")

            if mapped_df.empty:
                mapped_df = pd.DataFrame(columns=IMPORT_COLUMNS)
            else:
                mapped_df = mapped_df.reset_index(drop=True)

            return MappedRedemptionResult(
                df=mapped_df,
                filtered_snapshot_ids=filtered_snapshot_ids,
                rejected_duplicates=rejected_duplicates,
            )
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

    def fetch_stock_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch and normalize underlying stock daily data for enrichment reconstruction.

        TuShare's ``daily`` endpoint is exposed here as an adapter-level method so
        orchestration code never reaches through provider internals such as
        ``provider.pro``. The method remains intentionally thin: provider call,
        basic column normalization, date normalization, and provider-error
        translation only.
        """
        try:
            if not tickers:
                return pd.DataFrame(columns=["stk_code", "time", "close"])

            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            frames = []
            for i in range(0, len(tickers), 100):
                batch = tickers[i : i + 100]
                df_batch = self.pro.daily(ts_code=",".join(batch), start_date=ts_start, end_date=ts_end)
                if df_batch is not None and not df_batch.empty:
                    frames.append(df_batch)

            if not frames:
                return pd.DataFrame(columns=["stk_code", "time", "close"])

            df = pd.concat(frames)
            df = df.rename(columns={"ts_code": "stk_code", "trade_date": "time"})
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d")
            return df
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
            cal_df = self.pro.trade_cal(exchange="SSE", start_date=ts_start, end_date=ts_end, is_open="1")
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
            df = self.pro.trade_cal(exchange="SSE", start_date=ts_start, end_date=ts_end, is_open="1")
            return pd.to_datetime(df["cal_date"]).dt.strftime("%Y-%m-%d").tolist()
        except Exception as e:
            self._handle_exception(e)
