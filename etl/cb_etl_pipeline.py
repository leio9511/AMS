import json
import os
import datetime
import pandas as pd
import jqdatasdk

# Constants from jqdata_sync_cb.py
SUPPORTABILITY_BUCKET_SUPPORTABLE = "supportable"
SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO = "outside_basic_info"
SUPPORTABILITY_BUCKET_MISSING_COMPANY_CODE_LEGACY = "missing_company_code_legacy"
SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION = "unexpected_contract_regression"

SUPPORTABILITY_EXCLUSION_BUCKETS = {
    SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO: {
        "count_key": "filtered_bonds_outside_basic_info_count",
        "row_count_key": "filtered_rows_outside_basic_info_count",
        "codes_key": "filtered_bond_codes_outside_basic_info",
    },
    SUPPORTABILITY_BUCKET_MISSING_COMPANY_CODE_LEGACY: {
        "count_key": "filtered_bonds_missing_company_code_legacy_count",
        "row_count_key": "filtered_rows_missing_company_code_legacy_count",
        "codes_key": "filtered_bond_codes_missing_company_code_legacy",
    },
}

CANONICAL_CB_COLUMNS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "premium_rate",
    "double_low",
    "underlying_ticker",
    "is_st",
    "is_redeemed",
]

REDEMPTION_SOURCE_CONTRACT = {
    "source_table": "bond.CONBOND_BASIC_INFO",
    "primary_field": "delist_Date",
    "fallback_informational_fields": [
        "maturity_date",
        "last_cash_date",
        "convert_end_date",
    ],
    "null_primary_behavior": "is_redeemed=False",
}

# Stage Statuses
STAGE_STATUS_PASS = "PASS"
STAGE_STATUS_FAIL = "FAIL"
STAGE_STATUS_NOT_RUN = "NOT_RUN"

# Final Statuses
FINAL_STATUS_PASS = "PASS"
FINAL_STATUS_FAIL_ROOT_BLOCKER = "FAIL_ROOT_BLOCKER"
FINAL_STATUS_FAIL_SECONDARY_ONLY = "FAIL_SECONDARY_ONLY"

# Non-promotion disclaimer
NON_PROMOTION_DISCLAIMER = "[AUDIT-ONLY] This run is diagnostic only. No canonical dataset promotion was attempted."

def _split_bond_ticker(ticker: str) -> tuple[str | None, str | None]:
    if not isinstance(ticker, str) or "." not in ticker:
        return None, None

    bond_code_raw, bond_exchange_code = ticker.split(".", 1)
    bond_code_raw = bond_code_raw.strip()
    bond_exchange_code = bond_exchange_code.strip()
    if not bond_code_raw or not bond_exchange_code:
        return None, None
    return bond_code_raw, bond_exchange_code

def _prepare_basic_info_contract(df_bonds_info: pd.DataFrame) -> pd.DataFrame:
    columns = ["bond_code_raw", "company_code", "delist_Date"]
    if df_bonds_info is None or df_bonds_info.empty or "code" not in df_bonds_info.columns:
        return pd.DataFrame(columns=columns)

    working = df_bonds_info.copy()
    code_as_str = working["code"].apply(lambda value: str(value).strip() if pd.notna(value) else "")
    split_keys = code_as_str.apply(_split_bond_ticker)
    split_df = pd.DataFrame(
        split_keys.tolist(),
        columns=["bond_code_raw", "bond_exchange_code"],
        index=working.index,
    )
    working["bond_code_raw"] = split_df["bond_code_raw"].where(split_df["bond_code_raw"].notna(), code_as_str)
    working["bond_code_raw"] = working["bond_code_raw"].astype(str).str.strip()
    working = working[working["bond_code_raw"].ne("") & working["bond_code_raw"].ne("nan")]
    if working.empty:
        return pd.DataFrame(columns=columns)

    if "company_code" not in working.columns:
        working["company_code"] = pd.NA
    if "delist_Date" not in working.columns:
        working["delist_Date"] = pd.NaT

    working["delist_Date"] = pd.to_datetime(working["delist_Date"], errors="coerce")
    working = working.drop_duplicates(subset=["bond_code_raw"], keep="last")
    return working[columns].copy()

def _build_underlying_mapping(df_bonds_info: pd.DataFrame) -> dict:
    mapping_df = _prepare_basic_info_contract(df_bonds_info)
    if mapping_df.empty:
        return {}

    mapping_df = mapping_df.dropna(subset=["company_code"]).copy()
    if mapping_df.empty:
        return {}

    mapping_df = mapping_df.drop_duplicates(subset=["bond_code_raw"], keep="last")
    return mapping_df.set_index("bond_code_raw")["company_code"].to_dict()

def _build_delist_mapping(df_bonds_info: pd.DataFrame) -> dict:
    contract = REDEMPTION_SOURCE_CONTRACT
    mapping_df = _prepare_basic_info_contract(df_bonds_info)
    if mapping_df.empty:
        return {}

    mapping_df = mapping_df.drop_duplicates(subset=["bond_code_raw"], keep="last")
    return mapping_df.set_index("bond_code_raw")[contract["primary_field"]].to_dict()

def _build_bond_key_columns(df: pd.DataFrame, ticker_col: str = "ticker") -> pd.DataFrame:
    result = df.copy()
    if ticker_col not in result.columns:
        result["bond_code_raw"] = None
        result["bond_exchange_code"] = None
        return result

    normalized = result[ticker_col].apply(_split_bond_ticker)
    normalized_df = pd.DataFrame(
        normalized.tolist(),
        columns=["bond_code_raw", "bond_exchange_code"],
        index=result.index,
    )
    result[["bond_code_raw", "bond_exchange_code"]] = normalized_df
    return result

def _normalize_premium_source(df_premium: pd.DataFrame) -> pd.DataFrame:
    if df_premium is None or df_premium.empty:
        return pd.DataFrame(columns=["date", "bond_code_raw", "bond_exchange_code", "premium_rate"])

    required_columns = {"code", "date", "convert_premium_rate"}
    if not required_columns.issubset(df_premium.columns):
        raise ValueError("CONBOND_DAILY_CONVERT response missing required premium-rate columns")

    working = df_premium.copy()
    code_as_str = working["code"].astype(str)
    split_keys = code_as_str.apply(_split_bond_ticker)
    split_df = pd.DataFrame(
        split_keys.tolist(),
        columns=["code_from_ticker", "exchange_from_ticker"],
        index=working.index,
    )

    working["bond_code_raw"] = split_df["code_from_ticker"].where(split_df["code_from_ticker"].notna(), code_as_str)
    if "exchange_code" in working.columns:
        exchange_code = working["exchange_code"].astype(str)
        working["bond_exchange_code"] = exchange_code.where(exchange_code.ne("nan"), split_df["exchange_from_ticker"])
    else:
        working["bond_exchange_code"] = split_df["exchange_from_ticker"]

    working["date"] = pd.to_datetime(working["date"])
    working["premium_rate"] = working["convert_premium_rate"] / 100.0
    return working[["date", "bond_code_raw", "bond_exchange_code", "premium_rate"]]

def _extract_sorted_unique_codes(series: pd.Series) -> list[str]:
    if series is None or series.empty:
        return []

    normalized = series.dropna().astype(str).str.strip()
    normalized = normalized[
        normalized.ne("")
        & normalized.ne("nan")
        & normalized.ne("None")
    ]
    return sorted(normalized.unique().tolist())

def _build_empty_canonical_cb_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": pd.Series(dtype="object"),
            "date": pd.Series(dtype="datetime64[ns]"),
            "open": pd.Series(dtype="float64"),
            "high": pd.Series(dtype="float64"),
            "low": pd.Series(dtype="float64"),
            "close": pd.Series(dtype="float64"),
            "volume": pd.Series(dtype="float64"),
            "premium_rate": pd.Series(dtype="float64"),
            "double_low": pd.Series(dtype="float64"),
            "underlying_ticker": pd.Series(dtype="object"),
            "is_st": pd.Series(dtype="bool"),
            "is_redeemed": pd.Series(dtype="bool"),
        }
    )[CANONICAL_CB_COLUMNS]

class CBETLPipeline:
    def __init__(self, start_date: str, end_date: str, jqdata_provider=None):
        self.start_date = start_date
        self.end_date = end_date
        if jqdata_provider is None:
            import jqdatasdk
            self.jqdata_provider = jqdatasdk
        else:
            self.jqdata_provider = jqdata_provider
            
        self.results = {
            "source_coverage": {"status": STAGE_STATUS_NOT_RUN, "failure_type": "NONE", "message": ""},
            "supportability_summary": {"status": STAGE_STATUS_NOT_RUN, "failure_type": "NONE", "message": ""},
            "premium_join_summary": {"status": STAGE_STATUS_NOT_RUN, "failure_type": "NONE", "message": ""},
            "is_st_join_summary": {"status": STAGE_STATUS_NOT_RUN, "failure_type": "NONE", "message": ""},
            "redemption_summary": {"status": STAGE_STATUS_NOT_RUN, "failure_type": "NONE", "message": ""},
            "validator_summary": {"status": STAGE_STATUS_NOT_RUN, "failure_type": "NONE", "message": ""},
        }
        self.df = None
        self.df_bonds_info = None
        self.bond_to_stock = {}
        self.bond_to_delist = {}

    def run_stage_a_source_acquisition(self):
        stage = self.results["source_coverage"]
        stage["basic_info_row_count"] = 0
        stage["all_bond_security_count"] = 0
        stage["price_row_count"] = 0
        stage["price_unique_bond_count"] = 0
        stage["premium_source_row_count"] = 0
        stage["premium_source_unique_bond_count"] = 0
        stage["is_st_source_row_count"] = 0
        stage["is_st_source_unique_underlying_count"] = 0
        stage["redemption_source_row_count"] = 0
        stage["redemption_source_unique_bond_count"] = 0

        try:
            self.df_bonds_info = self.jqdata_provider.bond.run_query(self.jqdata_provider.query(self.jqdata_provider.bond.CONBOND_BASIC_INFO))
            stage["basic_info_row_count"] = len(self.df_bonds_info)
            
            self.bond_to_stock = _build_underlying_mapping(self.df_bonds_info)
            self.bond_to_delist = _build_delist_mapping(self.df_bonds_info)

            df_all_bonds = self.jqdata_provider.get_all_securities(["conbond"])
            stage["all_bond_security_count"] = len(df_all_bonds)
            tickers = df_all_bonds.index.tolist()

            df_price = self.jqdata_provider.get_price(
                tickers,
                start_date=self.start_date,
                end_date=self.end_date,
                frequency="daily",
                fields=["open", "high", "low", "close", "volume"],
            )
            stage["price_row_count"] = len(df_price)
            if not df_price.empty:
                if isinstance(df_price.index, pd.MultiIndex):
                     stage["price_unique_bond_count"] = len(df_price.index.get_level_values(0).unique())
                else:
                     stage["price_unique_bond_count"] = len(df_price["code"].unique()) if "code" in df_price.columns else 0

            if df_price.empty:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "PRICE_SOURCE_UNREADABLE"
                stage["message"] = "No price data found for the given range"
                return False

            self.df = df_price.reset_index()
            self.df.rename(columns={"time": "date", "code": "ticker"}, inplace=True)
            self.df["date"] = pd.to_datetime(self.df["date"])
            
            stage["status"] = STAGE_STATUS_PASS
            return True

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            if "auth" in str(e).lower() or "login" in str(e).lower() or "password" in str(e).lower():
                stage["failure_type"] = "SOURCE_AUTH_FAILURE"
            else:
                stage["failure_type"] = "PRICE_SOURCE_UNREADABLE"
            stage["message"] = str(e)
            return False

    def run_stage_b_supportability_classification(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["supportability_summary"]["status"] = STAGE_STATUS_NOT_RUN
            self.results["supportability_summary"]["message"] = "Skipped because Stage A failed."
            return False

        stage = self.results["supportability_summary"]
        stage["supportable_row_count"] = 0
        stage["supportable_unique_bond_count"] = 0
        stage["outside_basic_info_row_count"] = 0
        stage["outside_basic_info_unique_bond_count"] = 0
        stage["missing_company_code_legacy_row_count"] = 0
        stage["missing_company_code_legacy_unique_bond_count"] = 0
        stage["unexpected_contract_regression_row_count"] = 0
        stage["unexpected_contract_regression_unique_bond_count"] = 0
        stage["missing_underlying_row_count"] = 0
        stage["missing_underlying_unique_bond_count"] = 0

        try:
            self.df = _build_bond_key_columns(self.df, ticker_col="ticker")
            
            contract_df = _prepare_basic_info_contract(self.df_bonds_info)
            start_ts = pd.Timestamp(self.start_date)

            basic_info_codes = set(contract_df["bond_code_raw"].astype(str).tolist())
            supportable_codes = set(
                contract_df.loc[contract_df["company_code"].notna(), "bond_code_raw"].astype(str).tolist()
            )
            legacy_missing_company_code_codes = set(
                contract_df.loc[
                    contract_df["company_code"].isna()
                    & contract_df["delist_Date"].notna()
                    & (contract_df["delist_Date"] < start_ts),
                    "bond_code_raw",
                ].astype(str).tolist()
            )

            normalized_code = self.df["bond_code_raw"].where(self.df["bond_code_raw"].notna(), "").astype(str).str.strip()
            valid_code = normalized_code.ne("") & normalized_code.ne("nan") & normalized_code.ne("None")

            is_supportable = valid_code & normalized_code.isin(supportable_codes)
            is_outside_basic_info = valid_code & ~normalized_code.isin(basic_info_codes)
            is_missing_company_code_legacy = valid_code & normalized_code.isin(legacy_missing_company_code_codes)

            self.df["supportability_bucket"] = SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION
            self.df.loc[is_supportable, "supportability_bucket"] = SUPPORTABILITY_BUCKET_SUPPORTABLE
            self.df.loc[is_outside_basic_info, "supportability_bucket"] = SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO
            self.df.loc[is_missing_company_code_legacy, "supportability_bucket"] = SUPPORTABILITY_BUCKET_MISSING_COMPANY_CODE_LEGACY
            
            # Fill counts
            stage["supportable_row_count"] = int(is_supportable.sum())
            stage["supportable_unique_bond_count"] = int(self.df.loc[is_supportable, "bond_code_raw"].nunique())
            stage["outside_basic_info_row_count"] = int(is_outside_basic_info.sum())
            stage["outside_basic_info_unique_bond_count"] = int(self.df.loc[is_outside_basic_info, "bond_code_raw"].nunique())
            stage["missing_company_code_legacy_row_count"] = int(is_missing_company_code_legacy.sum())
            stage["missing_company_code_legacy_unique_bond_count"] = int(self.df.loc[is_missing_company_code_legacy, "bond_code_raw"].nunique())
            
            is_regression = self.df["supportability_bucket"] == SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION
            stage["unexpected_contract_regression_row_count"] = int(is_regression.sum())
            stage["unexpected_contract_regression_unique_bond_count"] = int(self.df.loc[is_regression, "bond_code_raw"].nunique())
            
            # Count missing underlying for symptoms
            df_supportable = self.df[is_supportable].copy()
            df_supportable["underlying"] = df_supportable["bond_code_raw"].map(self.bond_to_stock)
            missing_underlying_mask = df_supportable["underlying"].isna()
            stage["missing_underlying_row_count"] = int(missing_underlying_mask.sum())
            stage["missing_underlying_unique_bond_count"] = int(df_supportable.loc[missing_underlying_mask, "bond_code_raw"].nunique())

            if stage["unexpected_contract_regression_row_count"] > 0:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "SUPPORTABILITY_REGRESSION"
                stage["message"] = "Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"
            else:
                stage["status"] = STAGE_STATUS_PASS
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def run_stage_c_premium_join(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["premium_join_summary"]["status"] = STAGE_STATUS_NOT_RUN
            self.results["premium_join_summary"]["message"] = "Skipped because Stage A failed."
            return False

        stage = self.results["premium_join_summary"]
        stage["premium_joined_row_count"] = 0
        stage["premium_joined_unique_bond_count"] = 0
        stage["missing_premium_row_count"] = 0
        stage["missing_premium_unique_bond_count"] = 0
        stage["missing_premium_ratio"] = 0.0

        try:
            if self.df is None:
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No data to join premium rate."
                return True
                
            df_work = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_work.empty:
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No supportable bonds to join premium rate."
                return True

            df_work["underlying_ticker"] = df_work["bond_code_raw"].map(self.bond_to_stock)
            
            raw_codes = [code for code in df_work["bond_code_raw"].dropna().astype(str).unique().tolist() if code]
            if raw_codes:
                q = self.jqdata_provider.query(self.jqdata_provider.bond.CONBOND_DAILY_CONVERT).filter(
                    self.jqdata_provider.bond.CONBOND_DAILY_CONVERT.code.in_(raw_codes),
                    self.jqdata_provider.bond.CONBOND_DAILY_CONVERT.date >= self.start_date,
                    self.jqdata_provider.bond.CONBOND_DAILY_CONVERT.date <= self.end_date,
                )
                df_premium_raw = self.jqdata_provider.bond.run_query(q)
                self.results["source_coverage"]["premium_source_row_count"] = len(df_premium_raw)
                self.results["source_coverage"]["premium_source_unique_bond_count"] = df_premium_raw["code"].nunique() if "code" in df_premium_raw.columns else 0
                
                df_premium = _normalize_premium_source(df_premium_raw)
                if not df_premium.empty:
                    df_work = pd.merge(df_work, df_premium, on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
                else:
                    df_work["premium_rate"] = float("nan")
            else:
                df_work["premium_rate"] = float("nan")

            stage["premium_joined_row_count"] = int(df_work["premium_rate"].notna().sum())
            stage["premium_joined_unique_bond_count"] = int(df_work.loc[df_work["premium_rate"].notna(), "bond_code_raw"].nunique())
            stage["missing_premium_row_count"] = int(df_work["premium_rate"].isna().sum())
            stage["missing_premium_unique_bond_count"] = int(df_work.loc[df_work["premium_rate"].isna(), "bond_code_raw"].nunique())
            
            total_rows = len(df_work)
            stage["missing_premium_ratio"] = stage["missing_premium_row_count"] / total_rows if total_rows > 0 else 0.0
            
            # Classification
            supportable_row_count = self.results["supportability_summary"]["supportable_row_count"]
            premium_source_row_count = self.results["source_coverage"]["premium_source_row_count"]
            
            if supportable_row_count >= 50000 and premium_source_row_count == 5000 and stage["missing_premium_ratio"] >= 0.80:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "PREMIUM_SOURCE_TRUNCATION"
            elif supportable_row_count > 0 and stage["missing_premium_ratio"] >= 0.20:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "PREMIUM_RATE_MISSING_BROAD_COVERAGE"
            else:
                stage["status"] = STAGE_STATUS_PASS
            
            if "premium_rate" in self.df.columns:
                 self.df.drop(columns=["premium_rate"], inplace=True)
            
            self.df = pd.merge(self.df, df_work[["date", "bond_code_raw", "bond_exchange_code", "premium_rate", "underlying_ticker"]], 
                               on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def run_stage_d_is_st_join(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["is_st_join_summary"]["status"] = STAGE_STATUS_NOT_RUN
            self.results["is_st_join_summary"]["message"] = "Skipped because Stage A failed."
            return False

        stage = self.results["is_st_join_summary"]
        stage["is_st_joined_row_count"] = 0
        stage["is_st_joined_unique_bond_count"] = 0
        stage["missing_is_st_row_count"] = 0
        stage["missing_is_st_unique_bond_count"] = 0
        stage["missing_is_st_ratio"] = 0.0

        try:
            df_work = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_work.empty:
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No supportable bonds to join is_st."
                return True

            underlying_tickers = [
                ticker for ticker in df_work["underlying_ticker"].dropna().astype(str).unique().tolist() if ticker
            ]
            if underlying_tickers:
                df_st = self.jqdata_provider.get_extras("is_st", underlying_tickers, start_date=self.start_date, end_date=self.end_date)
                self.results["source_coverage"]["is_st_source_row_count"] = len(df_st) * len(df_st.columns) if not df_st.empty else 0
                self.results["source_coverage"]["is_st_source_unique_underlying_count"] = len(df_st.columns)
                
                st_long = df_st.stack().reset_index()
                st_long.columns = ["date", "underlying_ticker", "is_st"]
                st_long["date"] = pd.to_datetime(st_long["date"])

                df_work = pd.merge(df_work, st_long, on=["date", "underlying_ticker"], how="left")
            
            stage["is_st_joined_row_count"] = int(df_work["is_st"].notna().sum())
            stage["is_st_joined_unique_bond_count"] = int(df_work.loc[df_work["is_st"].notna(), "bond_code_raw"].nunique())
            stage["missing_is_st_row_count"] = int(df_work["is_st"].isna().sum())
            stage["missing_is_st_unique_bond_count"] = int(df_work.loc[df_work["is_st"].isna(), "bond_code_raw"].nunique())
            
            total_rows = len(df_work)
            stage["missing_is_st_ratio"] = stage["missing_is_st_row_count"] / total_rows if total_rows > 0 else 0.0
            
            if total_rows > 0 and stage["missing_is_st_ratio"] >= 0.20:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "IS_ST_SOURCE_GAP"
            else:
                stage["status"] = STAGE_STATUS_PASS

            if "is_st" in self.df.columns:
                self.df.drop(columns=["is_st"], inplace=True)
            self.df = pd.merge(self.df, df_work[["date", "bond_code_raw", "bond_exchange_code", "is_st"]], 
                               on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def run_stage_e_redemption_delist(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["redemption_summary"]["status"] = STAGE_STATUS_NOT_RUN
            self.results["redemption_summary"]["message"] = "Skipped because Stage A failed."
            return False

        stage = self.results["redemption_summary"]
        stage["redemption_joined_row_count"] = 0
        stage["redemption_joined_unique_bond_count"] = 0
        stage["missing_redemption_row_count"] = 0
        stage["missing_redemption_unique_bond_count"] = 0
        stage["missing_redemption_ratio"] = 0.0

        try:
            df_work = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_work.empty:
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No supportable bonds to derive redemption."
                return True

            df_work["delist_Date"] = pd.to_datetime(df_work["bond_code_raw"].map(self.bond_to_delist), errors="coerce")
            
            if self.df_bonds_info is not None:
                self.results["source_coverage"]["redemption_source_row_count"] = len(self.df_bonds_info)
                self.results["source_coverage"]["redemption_source_unique_bond_count"] = self.df_bonds_info["code"].nunique() if "code" in self.df_bonds_info.columns else 0

            stage["redemption_joined_row_count"] = int(df_work["delist_Date"].notna().sum())
            stage["redemption_joined_unique_bond_count"] = int(df_work.loc[df_work["delist_Date"].notna(), "bond_code_raw"].nunique())
            stage["missing_redemption_row_count"] = int(df_work["delist_Date"].isna().sum())
            stage["missing_redemption_unique_bond_count"] = int(df_work.loc[df_work["delist_Date"].isna(), "bond_code_raw"].nunique())
            
            total_rows = len(df_work)
            stage["missing_redemption_ratio"] = stage["missing_redemption_row_count"] / total_rows if total_rows > 0 else 0.0

            if total_rows > 0 and stage["missing_redemption_ratio"] >= 0.20:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "REDEMPTION_SOURCE_GAP"
            else:
                stage["status"] = STAGE_STATUS_PASS

            df_work["is_redeemed"] = df_work["delist_Date"].notna() & (df_work["date"] >= df_work["delist_Date"])
            
            if "is_redeemed" in self.df.columns:
                self.df.drop(columns=["is_redeemed"], inplace=True)
            self.df = pd.merge(self.df, df_work[["date", "bond_code_raw", "bond_exchange_code", "is_redeemed"]], 
                               on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
            
            if "premium_rate" in self.df.columns and "close" in self.df.columns:
                 self.df["double_low"] = self.df["close"] + self.df["premium_rate"] * 100
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def run_stage_f_validator(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["validator_summary"]["status"] = STAGE_STATUS_NOT_RUN
            self.results["validator_summary"]["message"] = "Skipped because Stage A failed."
            return False

        stage = self.results["validator_summary"]
        stage["schema_validator_status"] = STAGE_STATUS_NOT_RUN
        stage["semantic_validator_status"] = STAGE_STATUS_NOT_RUN
        stage["drift_validator_status"] = STAGE_STATUS_NOT_RUN
        stage["schema_validator_message"] = ""
        stage["semantic_validator_message"] = ""
        stage["drift_validator_message"] = ""
        stage["failure_type"] = "NONE"

        try:
            df_work = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_work.empty:
                stage["status"] = STAGE_STATUS_PASS
                stage["message"] = "No supportable bonds to validate."
                return True

            from ams.validators.cb_data_validator import CBDataValidator, DatasetSemanticValidator
            
            validator_l1 = CBDataValidator()
            validator_l2 = DatasetSemanticValidator()
            
            missing_cols = [c for c in CANONICAL_CB_COLUMNS if c not in df_work.columns]
            if missing_cols:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "VALIDATOR_SCHEMA_FAILURE"
                stage["message"] = f"Validator skipped because required canonical columns are missing after upstream stage failures: {missing_cols}"
                stage["schema_validator_status"] = STAGE_STATUS_FAIL
                stage["schema_validator_message"] = stage["message"]
                return False

            df_to_val = df_work[CANONICAL_CB_COLUMNS].copy()
            df_to_val["ticker"] = df_to_val["ticker"].astype(str)
            df_to_val["close"] = df_to_val["close"].astype(float)
            df_to_val["premium_rate"] = df_to_val["premium_rate"].astype(float)
            df_to_val["is_st"] = df_to_val["is_st"].astype(bool)
            df_to_val["is_redeemed"] = df_to_val["is_redeemed"].astype(bool)

            # Stage F.1: Schema Validator
            try:
                val_l1 = validator_l1.validate_dataframe(df_to_val)
                stage["schema_validator_status"] = STAGE_STATUS_PASS if val_l1 else STAGE_STATUS_FAIL
            except Exception as e:
                stage["schema_validator_status"] = STAGE_STATUS_FAIL
                stage["schema_validator_message"] = str(e)
            
            # Stage F.2: Semantic Validator
            try:
                val_l2 = validator_l2.validate_dataframe(df_to_val)
                stage["semantic_validator_status"] = STAGE_STATUS_PASS if val_l2 else STAGE_STATUS_FAIL
            except Exception as e:
                stage["semantic_validator_status"] = STAGE_STATUS_FAIL
                stage["semantic_validator_message"] = str(e)

            # Stage F.3: Drift Validator (NOT_RUN in v1 runtime)
            stage["drift_validator_status"] = STAGE_STATUS_NOT_RUN
            stage["drift_validator_message"] = "No dedicated validator path exists in v1 runtime."

            if stage["schema_validator_status"] == STAGE_STATUS_FAIL:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "VALIDATOR_SCHEMA_FAILURE"
                stage["message"] = f"Schema validation failed: {stage['schema_validator_message']}" if stage['schema_validator_message'] else "Schema validation failed"
            elif stage["semantic_validator_status"] == STAGE_STATUS_FAIL:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "VALIDATOR_SEMANTIC_FAILURE"
                stage["message"] = f"Semantic validation failed: {stage['semantic_validator_message']}" if stage['semantic_validator_message'] else "Semantic validation failed"
            else:
                stage["status"] = STAGE_STATUS_PASS
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def compute_findings(self):
        root_blockers = []
        secondary_findings = []

        if self.results["source_coverage"]["failure_type"] == "SOURCE_AUTH_FAILURE":
            root_blockers.append({"type": "SOURCE_AUTH_FAILURE", "stage": "A", "trigger": self.results["source_coverage"]["message"], "evidence": {}})
        if self.results["source_coverage"]["failure_type"] == "PRICE_SOURCE_UNREADABLE":
            root_blockers.append({"type": "PRICE_SOURCE_UNREADABLE", "stage": "A", "trigger": self.results["source_coverage"]["message"], "evidence": {}})
        if self.results["supportability_summary"]["failure_type"] == "SUPPORTABILITY_REGRESSION":
            root_blockers.append({"type": "SUPPORTABILITY_REGRESSION", "stage": "B", "trigger": "unexpected_contract_regression_row_count > 0", "evidence": {"count": self.results["supportability_summary"]["unexpected_contract_regression_row_count"]}})
        if self.results["premium_join_summary"]["failure_type"] == "PREMIUM_SOURCE_TRUNCATION":
            root_blockers.append({"type": "PREMIUM_SOURCE_TRUNCATION", "stage": "C", "trigger": "Exact formula match", "evidence": {"ratio": self.results["premium_join_summary"]["missing_premium_ratio"]}})
        if self.results["premium_join_summary"]["failure_type"] == "PREMIUM_RATE_MISSING_BROAD_COVERAGE":
            root_blockers.append({"type": "PREMIUM_RATE_MISSING_BROAD_COVERAGE", "stage": "C", "trigger": "missing_premium_ratio >= 0.20", "evidence": {"ratio": self.results["premium_join_summary"]["missing_premium_ratio"]}})
        if self.results["is_st_join_summary"]["failure_type"] == "IS_ST_SOURCE_GAP":
            root_blockers.append({"type": "IS_ST_SOURCE_GAP", "stage": "D", "trigger": "missing_is_st_ratio >= 0.20", "evidence": {"ratio": self.results["is_st_join_summary"]["missing_is_st_ratio"]}})
        if self.results["redemption_summary"]["failure_type"] == "REDEMPTION_SOURCE_GAP":
            root_blockers.append({"type": "REDEMPTION_SOURCE_GAP", "stage": "E", "trigger": "missing_redemption_ratio >= 0.20", "evidence": {"ratio": self.results["redemption_summary"]["missing_redemption_ratio"]}})
        if self.results["validator_summary"]["failure_type"] == "VALIDATOR_SCHEMA_FAILURE":
            root_blockers.append({"type": "VALIDATOR_SCHEMA_FAILURE", "stage": "F", "trigger": self.results["validator_summary"]["schema_validator_message"], "evidence": {}})
        if self.results["validator_summary"]["failure_type"] == "VALIDATOR_SEMANTIC_FAILURE":
            root_blockers.append({"type": "VALIDATOR_SEMANTIC_FAILURE", "stage": "F", "trigger": self.results["validator_summary"]["semantic_validator_message"], "evidence": {}})
        if self.results["validator_summary"]["failure_type"] == "VALIDATOR_DRIFT_FAILURE":
            root_blockers.append({"type": "VALIDATOR_DRIFT_FAILURE", "stage": "F", "trigger": self.results["validator_summary"]["drift_validator_message"], "evidence": {}})

        if self.results["supportability_summary"].get("missing_underlying_row_count", 0) > 0:
            secondary_findings.append({"type": "MISSING_UNDERLYING_TICKER_ROWS", "stage": "B", "trigger": "missing_underlying_row_count > 0", "evidence": {"count": self.results["supportability_summary"]["missing_underlying_row_count"]}})
        if self.results["premium_join_summary"].get("missing_premium_row_count", 0) > 0:
             secondary_findings.append({"type": "MISSING_PREMIUM_RATE_ROWS", "stage": "C", "trigger": "missing_premium_row_count > 0", "evidence": {"count": self.results["premium_join_summary"]["missing_premium_row_count"]}})
        if self.results["is_st_join_summary"].get("missing_is_st_row_count", 0) > 0:
             secondary_findings.append({"type": "MISSING_IS_ST_ROWS", "stage": "D", "trigger": "missing_is_st_row_count > 0", "evidence": {"count": self.results["is_st_join_summary"]["missing_is_st_row_count"]}})
        if self.results["redemption_summary"].get("missing_redemption_row_count", 0) > 0:
             secondary_findings.append({"type": "MISSING_REDEMPTION_ROWS", "stage": "E", "trigger": "missing_redemption_row_count > 0", "evidence": {"count": self.results["redemption_summary"]["missing_redemption_row_count"]}})
        if self.results["supportability_summary"]["status"] == STAGE_STATUS_PASS and self.results["supportability_summary"]["supportable_row_count"] == 0:
             secondary_findings.append({"type": "EXCLUSION_ONLY_WINDOW", "stage": "B", "trigger": "supportable_row_count == 0", "evidence": {}})
        
        return root_blockers, secondary_findings

    def get_final_report(self):
        root_blockers, secondary_findings = self.compute_findings()
        
        final_status = FINAL_STATUS_PASS
        if len(root_blockers) > 0:
            final_status = FINAL_STATUS_FAIL_ROOT_BLOCKER
        elif len(secondary_findings) > 0:
            final_status = FINAL_STATUS_FAIL_SECONDARY_ONLY
            
        report = {
            "execution_mode": "audit",
            "start_date": self.start_date,
            "end_date": self.end_date,
            "final_status": final_status,
            "non_promotion_disclaimer": NON_PROMOTION_DISCLAIMER,
            "source_coverage": self.results["source_coverage"],
            "supportability_summary": self.results["supportability_summary"],
            "premium_join_summary": self.results["premium_join_summary"],
            "is_st_join_summary": self.results["is_st_join_summary"],
            "redemption_summary": self.results["redemption_summary"],
            "validator_summary": self.results["validator_summary"],
            "root_blockers": root_blockers,
            "secondary_findings": secondary_findings,
        }
        return report
