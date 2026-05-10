import pandas as pd
from etl.cb_provider_base import BaseDataProvider, DataProviderAuthError
from etl.cb_audit_contract import (
    NON_PROMOTION_DISCLAIMER,
    FINAL_STATUS_PASS,
    FINAL_STATUS_FAIL_ROOT_BLOCKER,
    FINAL_STATUS_FAIL_SECONDARY_ONLY,
    PROMOTION_STATUS_BLOCKED,
    PROMOTION_STATUS_PASS,
    PROMOTION_STATUS_NOT_RUN,
    STAGE_STATUS_DEGRADED,
    STAGE_STATUS_FAIL,
    STAGE_STATUS_NOT_RUN,
    STAGE_STATUS_PASS,
    build_final_report,
    build_is_st_join_summary,
    build_pipeline_results,
    build_premium_join_summary,
    JQDATA_CONVERT_PRICE_PROVENANCE,
    build_redemption_summary,
    build_root_blocker,
    build_secondary_finding,
    build_source_coverage,
    build_supportability_summary,
    build_validator_summary,
    ensure_issue_1218_witness,
)
from etl.cb_field_registry import CANONICAL_CB_COLUMNS, CORE_VALIDATOR_COLUMNS

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

ENRICHMENT_DEGRADED_FAILURE_TYPES = {
    "RATE_LIMITED_ENRICHMENT",
    "PERMISSION_DEGRADED_ENRICHMENT",
}

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

def _normalize_premium_source(
    df_premium: pd.DataFrame,
    *,
    source_provider: str | None = None,
    convert_price_provenance_default: str | None = None,
) -> pd.DataFrame:
    output_columns = [
        "date",
        "bond_code_raw",
        "bond_exchange_code",
        "premium_rate",
        "convert_price",
        "convert_price_provenance",
    ]
    if df_premium is None or df_premium.empty:
        return pd.DataFrame(columns=output_columns)

    required_columns = {"code", "date", "convert_premium_rate"}
    if not required_columns.issubset(df_premium.columns):
        raise ValueError("CONBOND_DAILY_CONVERT response missing required premium-rate columns")

    working = df_premium.copy()

    if "convert_price" in working.columns:
        convert_price_non_null = working["convert_price"].notna()
        if convert_price_non_null.any():
            has_provenance = "convert_price_provenance" in working.columns
            if has_provenance:
                provenance = working["convert_price_provenance"]
                missing_provenance = provenance.isna() | provenance.astype(str).str.strip().eq("")
            else:
                missing_provenance = pd.Series(True, index=working.index)

            rows_requiring_default = convert_price_non_null & missing_provenance
            if rows_requiring_default.any():
                explicit_jqdata_source = source_provider == "jqdata"
                explicit_jqdata_default = convert_price_provenance_default == JQDATA_CONVERT_PRICE_PROVENANCE
                if not (explicit_jqdata_source or explicit_jqdata_default):
                    raise ValueError(
                        "convert_price_provenance is required when convert_price is non-null "
                        "unless the caller explicitly authorizes the exact JQData provenance default"
                    )

                if convert_price_provenance_default is not None and convert_price_provenance_default != JQDATA_CONVERT_PRICE_PROVENANCE:
                    raise ValueError("JQData convert_price provenance default must be exact")

                if "convert_price_provenance" not in working.columns:
                    working["convert_price_provenance"] = pd.NA
                working.loc[rows_requiring_default, "convert_price_provenance"] = JQDATA_CONVERT_PRICE_PROVENANCE
    else:
        working["convert_price"] = pd.NA

    if "convert_price_provenance" not in working.columns:
        working["convert_price_provenance"] = pd.NA

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
    return working[output_columns]

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
            "underlying_ticker": pd.Series(dtype="object"),
            "is_st": pd.Series(dtype="bool"),
            "redeem_risk": pd.Series(dtype="bool"),
            "is_redeemed": pd.Series(dtype="bool"),
            "premium_rate": pd.Series(dtype="float64"),
            "double_low": pd.Series(dtype="float64"),
            "convert_price": pd.Series(dtype="float64"),
            "convert_price_provenance": pd.Series(dtype="object"),
        }
    )[CANONICAL_CB_COLUMNS]

class CBETLPipeline:
    def __init__(self, start_date: str, end_date: str, provider: BaseDataProvider = None, **kwargs):
        self.start_date = start_date
        self.end_date = end_date
        
        # Backward compatibility for tests passing jqdata_provider directly
        if provider is None and "jqdata_provider" in kwargs:
            from etl.jqdata_provider import JQDataProvider
            self.provider = JQDataProvider(jqdata_client=kwargs["jqdata_provider"])
        else:
            self.provider = provider
            
        self.results = build_pipeline_results()
        self.df = None
        self.df_bonds_info = None
        self.bond_to_stock = {}
        self.bond_to_delist = {}

    def run_stage_a_source_acquisition(self):
        stage = self.results["source_coverage"] = build_source_coverage(**self.results["source_coverage"])
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

        if self.provider is None:
            stage["status"] = STAGE_STATUS_FAIL
            stage["failure_type"] = "PRICE_SOURCE_UNREADABLE"
            stage["message"] = "No data provider provided to pipeline"
            return False

        try:
            self.df_bonds_info = self.provider.fetch_cb_basic()
            stage["basic_info_row_count"] = len(self.df_bonds_info)
            
            self.bond_to_stock = _build_underlying_mapping(self.df_bonds_info)
            self.bond_to_delist = _build_delist_mapping(self.df_bonds_info)

            df_all_bonds = self.provider.fetch_all_securities(["conbond"])
            stage["all_bond_security_count"] = len(df_all_bonds)
            tickers = df_all_bonds.index.tolist()

            df_price = self.provider.fetch_cb_daily(
                tickers,
                start_date=self.start_date,
                end_date=self.end_date
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
            
            # --- START OF ACTIVE UNIVERSE FILTERING ---
            ohlcv_cols = ["open", "high", "low", "close", "volume"]
            missing_cols = [c for c in ohlcv_cols if c not in self.df.columns]
            for c in missing_cols:
                self.df[c] = pd.NA

            aus = self.results["active_universe_summary"]
            aus["core_price_row_count_before_filter"] = len(self.df)
            
            mask_all_null = self.df[ohlcv_cols].isnull().all(axis=1)
            aus["all_null_ohlcv_row_count_filtered"] = int(mask_all_null.sum())
            
            mask_active = self.df[ohlcv_cols].notna().all(axis=1)
            self.df = self.df[mask_active].copy()
            aus["core_price_row_count_after_filter"] = len(self.df)
            aus["core_universe_row_count"] = len(self.df)
            aus["core_universe_unique_bond_count"] = int(self.df["ticker"].nunique()) if not self.df.empty else 0
            aus["active_bond_universe_count"] = aus["core_universe_unique_bond_count"]
            # --- END OF ACTIVE UNIVERSE FILTERING ---
            
            stage["status"] = STAGE_STATUS_PASS
            return True

        except DataProviderAuthError as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["failure_type"] = "SOURCE_AUTH_FAILURE"
            stage["message"] = str(e)
            return False
        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["failure_type"] = "PRICE_SOURCE_UNREADABLE"
            stage["message"] = str(e)
            return False

    def run_stage_b_supportability_classification(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["supportability_summary"].update(
                {
                    "status": STAGE_STATUS_NOT_RUN,
                    "failure_type": "NONE",
                    "message": "Skipped because Stage A failed.",
                }
            )
            return False

        stage = self.results["supportability_summary"] = build_supportability_summary(**self.results["supportability_summary"])
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
            
            # Populate underlying_ticker for supportable bonds
            self.df["underlying_ticker"] = pd.NA
            self.df.loc[is_supportable, "underlying_ticker"] = self.df.loc[is_supportable, "bond_code_raw"].map(self.bond_to_stock)

            # Count missing underlying for symptoms
            missing_underlying_mask = is_supportable & self.df["underlying_ticker"].isna()
            stage["missing_underlying_row_count"] = int(missing_underlying_mask.sum())
            stage["missing_underlying_unique_bond_count"] = int(self.df.loc[missing_underlying_mask, "bond_code_raw"].nunique())

            if stage["missing_underlying_row_count"] > 0:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "SUPPORTABILITY_REGRESSION"
                stage["message"] = "Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"
                return False

            # --- ENRICHMENT TARGET UNIVERSE STATS ---
            enrichment_mask = is_supportable & self.df["underlying_ticker"].notna()
            aus = self.results["active_universe_summary"]
            aus["enrichment_target_row_count"] = int(enrichment_mask.sum())
            aus["enrichment_target_unique_bond_count"] = int(self.df.loc[enrichment_mask, "ticker"].nunique())
            # ----------------------------------------

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
            self.results["premium_join_summary"].update(
                {
                    "status": STAGE_STATUS_NOT_RUN,
                    "failure_type": "NONE",
                    "message": "Skipped because Stage A failed.",
                }
            )
            return False

        stage = self.results["premium_join_summary"] = build_premium_join_summary(**self.results["premium_join_summary"])
        stage["premium_joined_row_count"] = 0
        stage["premium_joined_unique_bond_count"] = 0
        stage["missing_premium_row_count"] = 0
        stage["missing_premium_unique_bond_count"] = 0
        stage["missing_premium_ratio"] = 0.0
        stage["rate_limited_enrichment"] = False
        stage["permission_degraded_enrichment"] = False
        stage["premium_missing_ratio_against_active_universe"] = 0.0

        try:
            if self.df is None:
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No data to join premium rate."
                return True
                
            df_work = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_work.empty:
                if "premium_rate" not in self.df.columns:
                    self.df["premium_rate"] = pd.Series(float("nan"), index=self.df.index)
                if "double_low" not in self.df.columns:
                    self.df["double_low"] = pd.Series(float("nan"), index=self.df.index)
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No supportable bonds to join premium rate."
                return True

            df_work["premium_rate"] = float("nan")
            
            # Assemble full tickers: bond_code_raw + . + bond_exchange_code
            valid_ticker_mask = df_work["bond_code_raw"].notna() & df_work["bond_exchange_code"].notna()
            tickers = (
                df_work.loc[valid_ticker_mask, "bond_code_raw"].astype(str) + 
                "." + 
                df_work.loc[valid_ticker_mask, "bond_exchange_code"].astype(str)
            ).unique().tolist()

            if tickers:
                df_premium = self._fetch_premium_batched(tickers, self.start_date, self.end_date)
                self.results["source_coverage"]["premium_source_row_count"] = len(df_premium)
                self.results["source_coverage"]["premium_source_unique_bond_count"] = df_premium["bond_code_raw"].nunique() if "bond_code_raw" in df_premium.columns else 0
                
                if not df_premium.empty:
                    df_work.drop(columns=["premium_rate"], inplace=True)
                    df_work = pd.merge(df_work, df_premium, on=["date", "bond_code_raw", "bond_exchange_code"], how="left")

            stage["premium_joined_row_count"] = int(df_work["premium_rate"].notna().sum())
            stage["premium_joined_unique_bond_count"] = int(df_work.loc[df_work["premium_rate"].notna(), "bond_code_raw"].nunique())
            stage["missing_premium_row_count"] = int(df_work["premium_rate"].isna().sum())
            stage["missing_premium_unique_bond_count"] = int(df_work.loc[df_work["premium_rate"].isna(), "bond_code_raw"].nunique())
            
            total_rows = len(df_work)
            stage["missing_premium_ratio"] = stage["missing_premium_row_count"] / total_rows if total_rows > 0 else 0.0
            
            df_enrichment = df_work[df_work["underlying_ticker"].notna()]
            enrichment_total = len(df_enrichment)
            if enrichment_total > 0:
                missing_in_enrichment = int(df_enrichment["premium_rate"].isna().sum())
                stage["premium_missing_ratio_against_active_universe"] = missing_in_enrichment / enrichment_total
            else:
                stage["premium_missing_ratio_against_active_universe"] = 0.0
            
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
            
            self.df = pd.merge(self.df, df_work[["date", "bond_code_raw", "bond_exchange_code", "premium_rate"]], 
                               on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
            
            if "premium_rate" in self.df.columns and "close" in self.df.columns:
                self.df["double_low"] = self.df["close"] + self.df["premium_rate"] * 100
            
            return stage["status"] == STAGE_STATUS_PASS

        except RuntimeError as e:
            enrichment_target_row_count = self.results["active_universe_summary"].get("enrichment_target_row_count", 0)
            enrichment_target_unique_bond_count = self.results["active_universe_summary"].get("enrichment_target_unique_bond_count", 0)
            if enrichment_target_row_count > 0:
                stage["missing_premium_row_count"] = enrichment_target_row_count
                stage["missing_premium_unique_bond_count"] = enrichment_target_unique_bond_count
                stage["missing_premium_ratio"] = 1.0
                stage["premium_missing_ratio_against_active_universe"] = 1.0
            if "RATE_LIMITED_ENRICHMENT" in str(e):
                stage["status"] = STAGE_STATUS_DEGRADED
                stage["failure_type"] = "RATE_LIMITED_ENRICHMENT"
                stage["rate_limited_enrichment"] = True
                stage["message"] = "TuShare cb_price_chg rate limit hit"
                return False
            if "PERMISSION_DEGRADED_ENRICHMENT" in str(e):
                stage["status"] = STAGE_STATUS_DEGRADED
                stage["failure_type"] = "PERMISSION_DEGRADED_ENRICHMENT"
                stage["permission_degraded_enrichment"] = True
                stage["message"] = "TuShare cb_price_chg permission degraded"
                return False
            if "single-call cap characteristic" in str(e):
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "PREMIUM_SOURCE_TRUNCATION"
                stage["message"] = str(e)
                # If we truncate, at least the difference between supportable universe and what we got is missing.
                # To satisfy audit secondary findings, we mark supportable count as missing if we aborted.
                stage["missing_premium_row_count"] = self.results["supportability_summary"].get("supportable_row_count", 0)
                return False
            if "CONCURRENT_RUN_BLOCKED" in str(e):
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "NONE"
                stage["message"] = str(e)
                stage["orchestrator_blocker_type"] = "CONCURRENT_RUN_BLOCKED"
                return False
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False
        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def _fetch_premium_batched(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame()
            
        try:
            if type(self.provider).__name__ == "TuShareProvider":
                from etl.tushare_enrichment_orchestrator import TuShareEnrichmentOrchestrator
                orchestrator = TuShareEnrichmentOrchestrator(self.provider)
                merged = orchestrator.run(tickers, start_date, end_date)
            else:
                merged = self.provider.fetch_cb_price_changes(tickers, start_date, end_date)
                
            if merged is None or merged.empty:
                return pd.DataFrame()
                
            source_provider = "jqdata" if type(self.provider).__name__ == "JQDataProvider" else None
            normalized = _normalize_premium_source(merged, source_provider=source_provider)
            return normalized.drop_duplicates(subset=["date", "bond_code_raw", "bond_exchange_code"])
        except Exception as e:
            from etl.cb_provider_base import DataProviderAuthError, DataProviderQuotaError
            if isinstance(e, DataProviderQuotaError) and "RATE_LIMITED" in str(e):
                 self.results["premium_join_summary"]["rate_limited_enrichment"] = True
                 raise RuntimeError("RATE_LIMITED_ENRICHMENT")
            if isinstance(e, DataProviderAuthError):
                 self.results["premium_join_summary"]["permission_degraded_enrichment"] = True
                 raise RuntimeError("PERMISSION_DEGRADED_ENRICHMENT")
            elif "single-call cap characteristic" in str(e):
                 raise RuntimeError(str(e))
            raise e

    def run_stage_d_is_st_join(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["is_st_join_summary"].update(
                {
                    "status": STAGE_STATUS_NOT_RUN,
                    "failure_type": "NONE",
                    "message": "Skipped because Stage A failed.",
                }
            )
            return False

        stage = self.results["is_st_join_summary"] = build_is_st_join_summary(**self.results["is_st_join_summary"])
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
                try:
                    df_st = self.provider.fetch_stock_st_by_date(underlying_tickers, start_date=self.start_date, end_date=self.end_date)
                except Exception as e:
                    err_msg = str(e).lower()
                    if any(kw in err_msg for kw in ["window", "range", "permission", "account", "support"]):
                        stage["status"] = STAGE_STATUS_FAIL
                        stage["failure_type"] = "IS_ST_SOURCE_GAP"
                        stage["message"] = f"is_st source query exceeded the provider-supported date window; effective-window handling or structured gap classification is required. {str(e)}"
                        return False
                    raise e

                self.results["source_coverage"]["is_st_source_row_count"] = len(df_st) * len(df_st.columns) if not df_st.empty else 0
                self.results["source_coverage"]["is_st_source_unique_underlying_count"] = len(df_st.columns)
                
                if not df_st.empty:
                    st_long = df_st.stack().reset_index()
                    st_long.columns = ["date", "underlying_ticker", "is_st"]
                    st_long["date"] = pd.to_datetime(st_long["date"])

                    df_work = pd.merge(df_work, st_long, on=["date", "underlying_ticker"], how="left")
            
            total_rows = len(df_work)
            stage["is_st_joined_row_count"] = int(df_work["is_st"].notna().sum()) if "is_st" in df_work.columns else 0
            stage["is_st_joined_unique_bond_count"] = int(df_work.loc[df_work["is_st"].notna(), "bond_code_raw"].nunique()) if "is_st" in df_work.columns else 0
            stage["missing_is_st_row_count"] = int(df_work["is_st"].isna().sum()) if "is_st" in df_work.columns else total_rows
            stage["missing_is_st_unique_bond_count"] = int(df_work.loc[df_work["is_st"].isna(), "bond_code_raw"].nunique()) if "is_st" in df_work.columns else int(df_work["bond_code_raw"].nunique())
            
            stage["missing_is_st_ratio"] = stage["missing_is_st_row_count"] / total_rows if total_rows > 0 else 0.0
            
            if total_rows > 0 and stage["missing_is_st_ratio"] >= 0.20:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "IS_ST_SOURCE_GAP"
                if stage["missing_is_st_ratio"] == 1.0:
                    stage["message"] = "is_st source query exceeded the provider-supported date window; effective-window handling or structured gap classification is required."
            else:
                stage["status"] = STAGE_STATUS_PASS

            if "is_st" in self.df.columns:
                self.df.drop(columns=["is_st"], inplace=True)
            
            merge_cols = ["date", "bond_code_raw", "bond_exchange_code"]
            if "is_st" in df_work.columns:
                merge_cols.append("is_st")
            self.df = pd.merge(self.df, df_work[merge_cols], 
                               on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def run_stage_e_redemption_delist(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["redemption_summary"].update(
                {
                    "status": STAGE_STATUS_NOT_RUN,
                    "failure_type": "NONE",
                    "message": "Skipped because Stage A failed.",
                }
            )
            return False

        stage = self.results["redemption_summary"] = build_redemption_summary(**self.results["redemption_summary"])
        stage["redemption_joined_row_count"] = 0
        stage["redemption_joined_unique_bond_count"] = 0
        stage["missing_redemption_row_count"] = 0
        stage["missing_redemption_unique_bond_count"] = 0
        stage["missing_redemption_ratio"] = 0.0

        try:
            # Evaluate redemption coverage ONLY against the Core Universe
            # specifically the supportable subset of the Core Universe
            df_core_universe_supportable = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_core_universe_supportable.empty:
                stage["status"] = STAGE_STATUS_NOT_RUN
                stage["message"] = "No supportable bonds in Core Universe to derive redemption."
                return True

            df_core_universe_supportable["delist_Date"] = pd.to_datetime(df_core_universe_supportable["bond_code_raw"].map(self.bond_to_delist), errors="coerce")
            
            if self.df_bonds_info is not None:
                self.results["source_coverage"]["redemption_source_row_count"] = len(self.df_bonds_info)
                self.results["source_coverage"]["redemption_source_unique_bond_count"] = self.df_bonds_info["code"].nunique() if "code" in self.df_bonds_info.columns else 0

            stage["redemption_joined_row_count"] = int(df_core_universe_supportable["delist_Date"].notna().sum())
            stage["redemption_joined_unique_bond_count"] = int(df_core_universe_supportable.loc[df_core_universe_supportable["delist_Date"].notna(), "bond_code_raw"].nunique())
            stage["missing_redemption_row_count"] = int(df_core_universe_supportable["delist_Date"].isna().sum())
            stage["missing_redemption_unique_bond_count"] = int(df_core_universe_supportable.loc[df_core_universe_supportable["delist_Date"].isna(), "bond_code_raw"].nunique())
            
            total_rows = len(df_core_universe_supportable)
            stage["missing_redemption_ratio"] = stage["missing_redemption_row_count"] / total_rows if total_rows > 0 else 0.0

            if total_rows > 0 and stage["missing_redemption_ratio"] >= 0.20 and stage["redemption_joined_row_count"] == 0:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "REDEMPTION_SOURCE_GAP"
            else:
                stage["status"] = STAGE_STATUS_PASS

            df_core_universe_supportable["is_redeemed"] = df_core_universe_supportable["delist_Date"].notna() & (
                df_core_universe_supportable["date"] >= df_core_universe_supportable["delist_Date"]
            )
            if "redeem_risk" in df_core_universe_supportable.columns:
                df_core_universe_supportable["redeem_risk"] = (
                    df_core_universe_supportable["redeem_risk"].fillna(False).astype(bool)
                )
            else:
                df_core_universe_supportable["redeem_risk"] = False
            
            if "is_redeemed" in self.df.columns:
                self.df.drop(columns=["is_redeemed"], inplace=True)
            if "redeem_risk" in self.df.columns:
                self.df.drop(columns=["redeem_risk"], inplace=True)
            self.df = pd.merge(
                self.df,
                df_core_universe_supportable[["date", "bond_code_raw", "bond_exchange_code", "redeem_risk", "is_redeemed"]], 
                on=["date", "bond_code_raw", "bond_exchange_code"],
                how="left",
            )
            
            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            return False

    def _compute_core_path_status(self) -> str:
        source_status = self.results["source_coverage"]["status"]
        if source_status != STAGE_STATUS_PASS:
            return source_status

        supportability_status = self.results["supportability_summary"]["status"]
        if supportability_status != STAGE_STATUS_PASS:
            return supportability_status

        supportable_row_count = self.results["supportability_summary"].get("supportable_row_count", 0)
        if supportable_row_count == 0:
            return STAGE_STATUS_PASS

        is_st_status = self.results["is_st_join_summary"]["status"]
        if is_st_status == STAGE_STATUS_FAIL:
            return STAGE_STATUS_FAIL
        if is_st_status == STAGE_STATUS_NOT_RUN:
            return STAGE_STATUS_NOT_RUN

        redemption_status = self.results["redemption_summary"]["status"]
        if redemption_status == STAGE_STATUS_NOT_RUN:
            return STAGE_STATUS_NOT_RUN
        return STAGE_STATUS_PASS

    def _compute_enrichment_path_status(self) -> str:
        premium_status = self.results["premium_join_summary"]["status"]
        if premium_status == STAGE_STATUS_DEGRADED:
            return STAGE_STATUS_DEGRADED
        if premium_status == STAGE_STATUS_FAIL:
            return STAGE_STATUS_FAIL
        if premium_status == STAGE_STATUS_NOT_RUN:
            return STAGE_STATUS_NOT_RUN

        enrichment_validator_status = self.results["validator_summary"].get("enrichment_validator_status", STAGE_STATUS_NOT_RUN)
        if enrichment_validator_status == STAGE_STATUS_DEGRADED:
            return STAGE_STATUS_DEGRADED
        if enrichment_validator_status == STAGE_STATUS_FAIL:
            return STAGE_STATUS_FAIL
        if enrichment_validator_status == STAGE_STATUS_NOT_RUN:
            return STAGE_STATUS_NOT_RUN
        return STAGE_STATUS_PASS

    def _compute_promotion_gate(self, core_path_status: str) -> tuple[str, str]:
        validator_summary = self.results["validator_summary"]

        if core_path_status != STAGE_STATUS_PASS:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: core_path_status != PASS"

        core_validator_status = validator_summary.get("core_validator_status", STAGE_STATUS_NOT_RUN)
        if core_validator_status != STAGE_STATUS_PASS:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: core_validator_status != PASS"

        if self.results["premium_join_summary"].get("rate_limited_enrichment") is True:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: rate_limited_enrichment == true"

        if self.results["premium_join_summary"].get("permission_degraded_enrichment") is True:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: permission_degraded_enrichment == true"

        if self.df is None or "premium_rate" not in self.df.columns:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: premium_rate column is missing"

        if self.df is None or "double_low" not in self.df.columns:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: double_low column is missing"

        enrichment_target_row_count = self.results["active_universe_summary"].get("enrichment_target_row_count", 0)
        premium_missing_ratio = self.results["premium_join_summary"].get("premium_missing_ratio_against_active_universe", 0.0)
        if enrichment_target_row_count > 0 and premium_missing_ratio > 0.05:
            return PROMOTION_STATUS_BLOCKED, "Promotion blocked: premium_missing_ratio_against_active_universe > 0.05"

        return PROMOTION_STATUS_PASS, ""

    def run_stage_f_validator(self):
        if self.results["source_coverage"]["status"] == STAGE_STATUS_FAIL:
            self.results["validator_summary"].update(
                {
                    "status": STAGE_STATUS_NOT_RUN,
                    "failure_type": "NONE",
                    "message": "Skipped because Stage A failed.",
                    "core_validator_status": STAGE_STATUS_NOT_RUN,
                    "core_validator_message": "",
                    "enrichment_validator_status": STAGE_STATUS_NOT_RUN,
                    "enrichment_validator_message": "",
                    "promotion_gate_status": PROMOTION_STATUS_NOT_RUN,
                    "promotion_gate_message": "",
                }
            )
            return False

        stage = self.results["validator_summary"] = build_validator_summary(**self.results["validator_summary"])
        stage["core_validator_status"] = STAGE_STATUS_NOT_RUN
        stage["core_validator_message"] = ""
        stage["enrichment_validator_status"] = STAGE_STATUS_NOT_RUN
        stage["enrichment_validator_message"] = ""
        stage["promotion_gate_status"] = STAGE_STATUS_NOT_RUN
        stage["promotion_gate_message"] = ""
        stage["failure_type"] = "NONE"

        premium_orchestrator_blocker = self.results["premium_join_summary"].get("orchestrator_blocker_type")
        premium_orchestrator_missing_columns = {"premium_rate", "double_low"}

        try:
            df_work = self.df[self.df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
            if df_work.empty:
                stage["status"] = STAGE_STATUS_PASS
                stage["message"] = "No supportable bonds to validate."
                stage["core_validator_status"] = STAGE_STATUS_PASS
                stage["enrichment_validator_status"] = STAGE_STATUS_NOT_RUN
                stage["promotion_gate_status"] = PROMOTION_STATUS_PASS
                return True

            from ams.validators.cb_data_validator import CBDataValidator, normalize_core_validator_frame

            validator_l1 = CBDataValidator()

            core_missing_cols = [c for c in CORE_VALIDATOR_COLUMNS if c not in df_work.columns]
            enrichment_missing_cols = [c for c in ("premium_rate", "double_low") if c not in df_work.columns]
            if core_missing_cols:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "VALIDATOR_SCHEMA_FAILURE"
                stage["message"] = f"Validator skipped because required canonical columns are missing after upstream stage failures: {core_missing_cols}"
                stage["core_validator_status"] = STAGE_STATUS_FAIL
                stage["core_validator_message"] = stage["message"]
                stage["promotion_gate_status"] = PROMOTION_STATUS_BLOCKED
                stage["promotion_gate_message"] = "Promotion blocked: core_validator_status != PASS"
                return False

            for col in sorted(enrichment_missing_cols):
                df_work[col] = pd.Series(float("nan"), index=df_work.index)

            df_core_to_val = normalize_core_validator_frame(df_work[CORE_VALIDATOR_COLUMNS].copy())

            val_l1 = validator_l1.validate_dataframe(df_core_to_val)
            stage["core_validator_status"] = STAGE_STATUS_PASS if val_l1 else STAGE_STATUS_FAIL
            if not val_l1 and getattr(validator_l1, "last_error_message", ""):
                stage["core_validator_message"] = validator_l1.last_error_message

            try:
                if premium_orchestrator_blocker == "CONCURRENT_RUN_BLOCKED":
                    stage["enrichment_validator_status"] = STAGE_STATUS_NOT_RUN
                    stage["enrichment_validator_message"] = ""
                else:
                    from ams.validators.cb_data_validator import EnrichmentValidator
                    validator_enrichment = EnrichmentValidator()
                    df_enrichment_target = df_work[df_work["underlying_ticker"].notna()].copy()
                    if not df_enrichment_target.empty:
                        st, msg = validator_enrichment.validate_dataframe(df_enrichment_target)
                        stage["enrichment_validator_status"] = st
                        stage["enrichment_validator_message"] = msg
                    else:
                        stage["enrichment_validator_status"] = STAGE_STATUS_NOT_RUN
                        stage["enrichment_validator_message"] = ""
            except Exception as e:
                stage["enrichment_validator_status"] = STAGE_STATUS_FAIL
                stage["enrichment_validator_message"] = str(e)

            if stage["core_validator_status"] == STAGE_STATUS_FAIL:
                stage["status"] = STAGE_STATUS_FAIL
                if stage["failure_type"] == "VALIDATOR_SEMANTIC_FAILURE":
                    stage["message"] = f"Semantic validation failed: {stage['core_validator_message']}" if stage["core_validator_message"] else "Semantic validation failed"
                else:
                    if stage["failure_type"] == "NONE":
                        stage["failure_type"] = "VALIDATOR_SCHEMA_FAILURE"
                    stage["message"] = f"Schema validation failed: {stage['core_validator_message']}" if stage["core_validator_message"] else "Schema validation failed"
            elif stage["enrichment_validator_status"] == STAGE_STATUS_FAIL:
                stage["status"] = STAGE_STATUS_FAIL
                stage["failure_type"] = "VALIDATOR_SEMANTIC_FAILURE"
                stage["message"] = f"Semantic validation failed: {stage['enrichment_validator_message']}" if stage["enrichment_validator_message"] else "Semantic validation failed"
            elif stage["enrichment_validator_status"] == STAGE_STATUS_DEGRADED:
                stage["status"] = STAGE_STATUS_DEGRADED
                stage["message"] = stage["enrichment_validator_message"]
            else:
                stage["status"] = STAGE_STATUS_PASS

            core_path_status = self._compute_core_path_status()
            promotion_status, promotion_message = self._compute_promotion_gate(core_path_status)
            stage["promotion_gate_status"] = promotion_status
            stage["promotion_gate_message"] = promotion_message

            return stage["status"] == STAGE_STATUS_PASS

        except Exception as e:
            stage["status"] = STAGE_STATUS_FAIL
            stage["message"] = str(e)
            stage["core_validator_status"] = STAGE_STATUS_FAIL
            stage["core_validator_message"] = str(e)
            stage["promotion_gate_status"] = PROMOTION_STATUS_BLOCKED
            stage["promotion_gate_message"] = "Promotion blocked: core_validator_status != PASS"
            return False

    def compute_findings(self):
        root_blockers = []
        secondary_findings = []

        if self.results["source_coverage"]["failure_type"] == "SOURCE_AUTH_FAILURE":
            root_blockers.append(build_root_blocker("SOURCE_AUTH_FAILURE", "A", self.results["source_coverage"]["message"], {}))
        if self.results["source_coverage"]["failure_type"] == "PRICE_SOURCE_UNREADABLE":
            root_blockers.append(build_root_blocker("PRICE_SOURCE_UNREADABLE", "A", self.results["source_coverage"]["message"], {}))
        if self.results["supportability_summary"]["failure_type"] == "SUPPORTABILITY_REGRESSION":
            root_blockers.append(build_root_blocker("SUPPORTABILITY_REGRESSION", "B", "unexpected_contract_regression_row_count > 0", {"count": self.results["supportability_summary"]["unexpected_contract_regression_row_count"]}))
        if self.results["premium_join_summary"]["failure_type"] == "PREMIUM_SOURCE_TRUNCATION":
            root_blockers.append(build_root_blocker("PREMIUM_SOURCE_TRUNCATION", "C", "Exact formula match", {"ratio": self.results["premium_join_summary"]["missing_premium_ratio"]}))
        if self.results["premium_join_summary"]["failure_type"] == "PREMIUM_RATE_MISSING_BROAD_COVERAGE":
            root_blockers.append(build_root_blocker("PREMIUM_RATE_MISSING_BROAD_COVERAGE", "C", "missing_premium_ratio >= 0.20", {"ratio": self.results["premium_join_summary"]["missing_premium_ratio"]}))
        if self.results["premium_join_summary"]["failure_type"] == "RATE_LIMITED_ENRICHMENT":
            root_blockers.append(build_root_blocker("RATE_LIMITED_ENRICHMENT", "ORCH", self.results["premium_join_summary"]["message"], {"rate_limited_enrichment": True}))
        if self.results["premium_join_summary"]["failure_type"] == "PERMISSION_DEGRADED_ENRICHMENT":
            root_blockers.append(build_root_blocker("PERMISSION_DEGRADED_ENRICHMENT", "ORCH", self.results["premium_join_summary"]["message"], {"permission_degraded_enrichment": True}))
        if self.results["premium_join_summary"].get("orchestrator_blocker_type") == "CONCURRENT_RUN_BLOCKED":
            root_blockers.append(build_root_blocker("CONCURRENT_RUN_BLOCKED", "ORCH", self.results["premium_join_summary"]["message"], {}))
        if self.results["is_st_join_summary"]["failure_type"] == "IS_ST_SOURCE_GAP":
            root_blockers.append(build_root_blocker("IS_ST_SOURCE_GAP", "D", "missing_is_st_ratio >= 0.20", {"ratio": self.results["is_st_join_summary"]["missing_is_st_ratio"]}))
        if self.results["redemption_summary"]["failure_type"] == "REDEMPTION_SOURCE_GAP":
            root_blockers.append(build_root_blocker("REDEMPTION_SOURCE_GAP", "E", "missing_redemption_ratio >= 0.20", {"ratio": self.results["redemption_summary"]["missing_redemption_ratio"]}))
        if self.results["validator_summary"]["failure_type"] == "VALIDATOR_SCHEMA_FAILURE":
            root_blockers.append(build_root_blocker("VALIDATOR_SCHEMA_FAILURE", "F", self.results["validator_summary"].get("core_validator_message", ""), {}))
        if self.results["validator_summary"]["failure_type"] == "VALIDATOR_SEMANTIC_FAILURE":
            trigger = self.results["validator_summary"].get("core_validator_message") or self.results["validator_summary"].get("enrichment_validator_message", "")
            root_blockers.append(build_root_blocker("VALIDATOR_SEMANTIC_FAILURE", "F", trigger, {}))

        if self.results["supportability_summary"].get("missing_underlying_row_count", 0) > 0:
            secondary_findings.append(build_secondary_finding("MISSING_UNDERLYING_TICKER_ROWS", "B", "missing_underlying_row_count > 0", {"count": self.results["supportability_summary"]["missing_underlying_row_count"]}))
        if self.results["premium_join_summary"].get("missing_premium_row_count", 0) > 0:
             secondary_findings.append(build_secondary_finding("MISSING_PREMIUM_RATE_ROWS", "C", "missing_premium_row_count > 0", {"count": self.results["premium_join_summary"]["missing_premium_row_count"]}))
        if self.results["is_st_join_summary"].get("missing_is_st_row_count", 0) > 0:
             secondary_findings.append(build_secondary_finding("MISSING_IS_ST_ROWS", "D", "missing_is_st_row_count > 0", {"count": self.results["is_st_join_summary"]["missing_is_st_row_count"]}))
        if self.results["redemption_summary"].get("missing_redemption_row_count", 0) > 0:
             secondary_findings.append(build_secondary_finding("MISSING_REDEMPTION_ROWS", "E", "missing_redemption_row_count > 0", {"count": self.results["redemption_summary"]["missing_redemption_row_count"]}))
        if self.results["supportability_summary"]["status"] == STAGE_STATUS_PASS and self.results["supportability_summary"]["supportable_row_count"] == 0:
             secondary_findings.append(build_secondary_finding("EXCLUSION_ONLY_WINDOW", "B", "supportable_row_count == 0", {}))

        return root_blockers, secondary_findings

    def get_final_report(self):
        root_blockers, secondary_findings = self.compute_findings()

        final_status = FINAL_STATUS_PASS
        if len(root_blockers) > 0:
            final_status = FINAL_STATUS_FAIL_ROOT_BLOCKER
        elif len(secondary_findings) > 0:
            final_status = FINAL_STATUS_FAIL_SECONDARY_ONLY

        core_path_status = self._compute_core_path_status()
        enrichment_path_status = self._compute_enrichment_path_status()
        promotion_status, promotion_message = self._compute_promotion_gate(core_path_status)
        self.results["validator_summary"]["promotion_gate_status"] = promotion_status
        self.results["validator_summary"]["promotion_gate_message"] = promotion_message

        report = build_final_report(
            start_date=self.start_date,
            end_date=self.end_date,
            final_status=final_status,
            core_path_status=core_path_status,
            enrichment_path_status=enrichment_path_status,
            results=self.results,
            root_blockers=root_blockers,
            secondary_findings=secondary_findings,
        )
        report["non_promotion_disclaimer"] = NON_PROMOTION_DISCLAIMER
        report = ensure_issue_1218_witness(report)
        return report
