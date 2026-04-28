import json
import os
import datetime

import jqdatasdk
import pandas as pd


METRICS_PATH = "/root/projects/AMS/data/cb_history_factors.metrics.json"
DATA_PATH = "/root/projects/AMS/data/cb_history_factors.csv"
LEGACY_UNDERLYING_SOURCE_FATAL = (
    "[FATAL] Invalid underlying-ticker source contract: get_security_info(ticker).parent "
    "is not valid for AMS convertible bonds."
)
LEGACY_REDEMPTION_SOURCE_FATAL = (
    "[FATAL] Invalid redemption source contract: finance.CCB_CALL is not a valid "
    "JQData table for AMS convertible-bond lifecycle semantics."
)
SUPPORTABILITY_REGRESSION_ERROR = "Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"
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


class ETLStage:
    def __init__(self, name: str):
        self.name = name

    def run(self, context: dict) -> dict:
        raise NotImplementedError


class SourceAcquisitionStage(ETLStage):
    def __init__(self, start_date: str, end_date: str):
        super().__init__("source_coverage")
        self.start_date = start_date
        self.end_date = end_date

    def run(self, context: dict) -> dict:
        summary = {
            "status": "PASS",
            "failure_type": "NONE",
            "basic_info_row_count": 0,
            "all_bond_security_count": 0,
            "price_row_count": 0,
            "price_unique_bond_count": 0,
            "premium_source_row_count": 0,
            "premium_source_unique_bond_count": 0,
            "is_st_source_row_count": 0,
            "is_st_source_unique_underlying_count": 0,
            "redemption_source_row_count": 0,
            "redemption_source_unique_bond_count": 0,
            "message": "",
        }

        user = os.environ.get("JQDATA_USER")
        pwd = os.environ.get("JQDATA_PWD")

        if not user or not pwd:
            summary["status"] = "FAIL"
            summary["failure_type"] = "SOURCE_AUTH_FAILURE"
            summary["message"] = "Missing JQDATA_USER or JQDATA_PWD environment variables"
            return summary

        try:
            jqdatasdk.auth(user, pwd)
        except Exception as e:
            summary["status"] = "FAIL"
            summary["failure_type"] = "SOURCE_AUTH_FAILURE"
            summary["message"] = f"JQData auth failed: {e}"
            return summary

        try:
            df_bonds_info = jqdatasdk.bond.run_query(jqdatasdk.query(jqdatasdk.bond.CONBOND_BASIC_INFO))
            context["df_bonds_info"] = df_bonds_info
            summary["basic_info_row_count"] = len(df_bonds_info)

            df_all_bonds = jqdatasdk.get_all_securities(["conbond"])
            tickers = df_all_bonds.index.tolist()
            summary["all_bond_security_count"] = len(tickers)

            df_price = jqdatasdk.get_price(
                tickers,
                start_date=self.start_date,
                end_date=self.end_date,
                frequency="daily",
                fields=["open", "high", "low", "close", "volume"],
            )
            if df_price.empty:
                summary["status"] = "FAIL"
                summary["failure_type"] = "PRICE_SOURCE_UNREADABLE"
                summary["message"] = "No price data found for the given range"
                return summary

            df = df_price.reset_index()
            df.rename(columns={"time": "date", "code": "ticker"}, inplace=True)
            df["date"] = pd.to_datetime(df["date"])
            context["df"] = df
            summary["price_row_count"] = len(df)
            summary["price_unique_bond_count"] = len(df["ticker"].unique())

        except Exception as e:
            summary["status"] = "FAIL"
            summary["failure_type"] = "PRICE_SOURCE_UNREADABLE"
            summary["message"] = f"Source acquisition failed: {e}"
            return summary

        return summary


class SupportabilityStage(ETLStage):
    def __init__(self, start_date: str):
        super().__init__("supportability_summary")
        self.start_date = start_date

    def run(self, context: dict) -> dict:
        summary = {
            "status": "PASS",
            "failure_type": "NONE",
            "supportable_row_count": 0,
            "supportable_unique_bond_count": 0,
            "outside_basic_info_row_count": 0,
            "outside_basic_info_unique_bond_count": 0,
            "missing_company_code_legacy_row_count": 0,
            "missing_company_code_legacy_unique_bond_count": 0,
            "unexpected_contract_regression_row_count": 0,
            "unexpected_contract_regression_unique_bond_count": 0,
            "missing_underlying_row_count": 0,
            "missing_underlying_unique_bond_count": 0,
            "message": "",
        }

        df = context.get("df")
        df_bonds_info = context.get("df_bonds_info")

        if df is None or df_bonds_info is None:
            summary["status"] = "NOT_RUN"
            summary["message"] = "Skipped because Stage A failed."
            return summary

        df = _build_bond_key_columns(df, ticker_col="ticker")
        df = _classify_supportability(df, df_bonds_info, self.start_date)
        context["df"] = df

        # Populate summary counts
        for bucket in [
            SUPPORTABILITY_BUCKET_SUPPORTABLE,
            SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO,
            SUPPORTABILITY_BUCKET_MISSING_COMPANY_CODE_LEGACY,
            SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION
        ]:
            mask = df["supportability_bucket"] == bucket
            count = int(mask.sum())
            unique_count = len(df.loc[mask, "ticker"].unique()) if "ticker" in df.columns else 0
            
            if bucket == SUPPORTABILITY_BUCKET_SUPPORTABLE:
                summary["supportable_row_count"] = count
                summary["supportable_unique_bond_count"] = unique_count
            elif bucket == SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO:
                summary["outside_basic_info_row_count"] = count
                summary["outside_basic_info_unique_bond_count"] = unique_count
            elif bucket == SUPPORTABILITY_BUCKET_MISSING_COMPANY_CODE_LEGACY:
                summary["missing_company_code_legacy_row_count"] = count
                summary["missing_company_code_legacy_unique_bond_count"] = unique_count
            elif bucket == SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION:
                summary["unexpected_contract_regression_row_count"] = count
                summary["unexpected_contract_regression_unique_bond_count"] = unique_count

        # Calculate missing underlying ticker counts (PRD 3.3 and Reviewer Feedback)
        bond_to_stock = _build_underlying_mapping(df_bonds_info)
        temp_underlying = df["bond_code_raw"].map(bond_to_stock)
        missing_mask = temp_underlying.isna()
        summary["missing_underlying_row_count"] = int(missing_mask.sum())
        summary["missing_underlying_unique_bond_count"] = len(df.loc[missing_mask, "ticker"].unique()) if "ticker" in df.columns else 0

        if summary["unexpected_contract_regression_row_count"] > 0:
            summary["status"] = "FAIL"
            summary["failure_type"] = "SUPPORTABILITY_REGRESSION"
            summary["message"] = SUPPORTABILITY_REGRESSION_ERROR

        return summary


class StagedPipeline:
    def __init__(self, stages: list[ETLStage]):
        self.stages = stages
        self.context = {
            "df": None,
            "df_bonds_info": None,
            "metrics": {},
            "stage_results": {}
        }

    def run(self, stop_on_failure: bool = True) -> dict:
        for stage in self.stages:
            result = stage.run(self.context)
            self.context["stage_results"][stage.name] = result
            if result.get("status") == "FAIL":
                if stop_on_failure:
                    self._mark_remaining_not_run(self.stages.index(stage) + 1, stage.name)
                    break
        return self.context["stage_results"]

    def _mark_remaining_not_run(self, start_index: int, failing_stage_name: str = "Stage A"):
        message = "Skipped because Stage A failed." if failing_stage_name == "source_coverage" else f"Skipped because {failing_stage_name} failed."
        for i in range(start_index, len(self.stages)):
            stage = self.stages[i]
            self.context["stage_results"][stage.name] = {
                "status": "NOT_RUN",
                "failure_type": "NONE",
                "message": message
            }


class CBETLAuditRunner:
    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.pipeline = StagedPipeline([
            SourceAcquisitionStage(start_date, end_date),
            SupportabilityStage(start_date),
        ])

    def _get_default_stage_c_summary(self, status="NOT_RUN", message=""):
        return {
            "status": status,
            "failure_type": "NONE",
            "premium_joined_row_count": 0,
            "premium_joined_unique_bond_count": 0,
            "missing_premium_row_count": 0,
            "missing_premium_unique_bond_count": 0,
            "missing_premium_ratio": 0.0,
            "message": message
        }

    def _get_default_stage_d_summary(self, status="NOT_RUN", message=""):
        return {
            "status": status,
            "failure_type": "NONE",
            "is_st_joined_row_count": 0,
            "is_st_joined_unique_bond_count": 0,
            "missing_is_st_row_count": 0,
            "missing_is_st_unique_bond_count": 0,
            "missing_is_st_ratio": 0.0,
            "message": message
        }

    def _get_default_stage_e_summary(self, status="NOT_RUN", message=""):
        return {
            "status": status,
            "failure_type": "NONE",
            "redemption_joined_row_count": 0,
            "redemption_joined_unique_bond_count": 0,
            "missing_redemption_row_count": 0,
            "missing_redemption_unique_bond_count": 0,
            "missing_redemption_ratio": 0.0,
            "message": message
        }

    def _get_default_stage_f_summary(self, status="NOT_RUN", message=""):
        return {
            "status": status,
            "failure_type": "NONE",
            "schema_validator_status": "NOT_RUN",
            "semantic_validator_status": "NOT_RUN",
            "drift_validator_status": "NOT_RUN",
            "schema_validator_message": "",
            "semantic_validator_message": "",
            "drift_validator_message": "",
            "message": message
        }

    def run(self) -> dict:
        stage_results = self.pipeline.run(stop_on_failure=False)
        
        source_coverage = stage_results.get("source_coverage", {})
        supportability_summary = stage_results.get("supportability_summary", {})
        
        # Handle NOT_RUN propagation for hardcoded stages C-F
        if source_coverage.get("status") == "FAIL":
            not_run_message = "Skipped because Stage A failed."
        elif supportability_summary.get("status") == "FAIL":
            not_run_message = "Skipped because supportability_summary failed."
        else:
            not_run_message = "Stage not implemented in v1 PR-001"

        # Build the final report according to PRD
        report = {
            "execution_mode": "audit",
            "start_date": self.start_date,
            "end_date": self.end_date,
            "final_status": "PASS",
            "non_promotion_disclaimer": "[AUDIT-ONLY] This run is diagnostic only. No canonical dataset promotion was attempted.",
            "source_coverage": source_coverage,
            "supportability_summary": supportability_summary,
            "premium_join_summary": self._get_default_stage_c_summary(message=not_run_message),
            "is_st_join_summary": self._get_default_stage_d_summary(message=not_run_message),
            "redemption_summary": self._get_default_stage_e_summary(message=not_run_message),
            "validator_summary": self._get_default_stage_f_summary(message=not_run_message),
            "root_blockers": [],
            "secondary_findings": []
        }

        # Root blockers calculation
        if report["source_coverage"].get("failure_type") == "SOURCE_AUTH_FAILURE":
            report["root_blockers"].append({
                "type": "SOURCE_AUTH_FAILURE",
                "stage": "A",
                "trigger": report["source_coverage"].get("message"),
                "evidence": {}
            })
        if report["source_coverage"].get("failure_type") == "PRICE_SOURCE_UNREADABLE":
            report["root_blockers"].append({
                "type": "PRICE_SOURCE_UNREADABLE",
                "stage": "A",
                "trigger": report["source_coverage"].get("message"),
                "evidence": {}
            })
        if report["supportability_summary"].get("failure_type") == "SUPPORTABILITY_REGRESSION":
            report["root_blockers"].append({
                "type": "SUPPORTABILITY_REGRESSION",
                "stage": "B",
                "trigger": report["supportability_summary"].get("message"),
                "evidence": {"unexpected_contract_regression_row_count": report["supportability_summary"].get("unexpected_contract_regression_row_count")}
            })

        # Secondary findings implementation (PRD 3.6)
        if report["supportability_summary"].get("missing_underlying_row_count", 0) > 0:
            report["secondary_findings"].append({
                "type": "MISSING_UNDERLYING_TICKER_ROWS",
                "stage": "B",
                "trigger": "missing_underlying_row_count > 0",
                "evidence": {
                    "missing_underlying_row_count": report["supportability_summary"].get("missing_underlying_row_count"),
                    "missing_underlying_unique_bond_count": report["supportability_summary"].get("missing_underlying_unique_bond_count")
                }
            })

        # Final status
        if report["root_blockers"]:
            report["final_status"] = "FAIL_ROOT_BLOCKER"
        elif report["secondary_findings"]:
            report["final_status"] = "FAIL_SECONDARY_ONLY"
        else:
            report["final_status"] = "PASS"

        # File writing side effect (PRD 3.10)
        report_filename = f"cb_etl_audit_{self.start_date}_{self.end_date}.json"
        report_path = os.path.join("/root/projects/AMS/reports", report_filename)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report


def _split_bond_ticker(ticker: str) -> tuple[str | None, str | None]:
    if not isinstance(ticker, str) or "." not in ticker:
        return None, None

    bond_code_raw, bond_exchange_code = ticker.split(".", 1)
    bond_code_raw = bond_code_raw.strip()
    bond_exchange_code = bond_exchange_code.strip()
    if not bond_code_raw or not bond_exchange_code:
        return None, None
    return bond_code_raw, bond_exchange_code


def _raise_legacy_underlying_source_error() -> None:
    raise RuntimeError(LEGACY_UNDERLYING_SOURCE_FATAL)


def _raise_legacy_redemption_source_error() -> None:
    raise RuntimeError(LEGACY_REDEMPTION_SOURCE_FATAL)


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


def _classify_supportability(df: pd.DataFrame, df_bonds_info: pd.DataFrame, start_date: str) -> pd.DataFrame:
    result = df.copy()
    contract_df = _prepare_basic_info_contract(df_bonds_info)
    start_ts = pd.Timestamp(start_date)

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

    normalized_code = result["bond_code_raw"].where(result["bond_code_raw"].notna(), "").astype(str).str.strip()
    valid_code = normalized_code.ne("") & normalized_code.ne("nan") & normalized_code.ne("None")

    is_supportable = valid_code & normalized_code.isin(supportable_codes)
    is_outside_basic_info = valid_code & ~normalized_code.isin(basic_info_codes)
    is_missing_company_code_legacy = valid_code & normalized_code.isin(legacy_missing_company_code_codes)

    result["supportability_bucket"] = SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION
    result.loc[is_supportable, "supportability_bucket"] = SUPPORTABILITY_BUCKET_SUPPORTABLE
    result.loc[is_outside_basic_info, "supportability_bucket"] = SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO
    result.loc[is_missing_company_code_legacy, "supportability_bucket"] = SUPPORTABILITY_BUCKET_MISSING_COMPANY_CODE_LEGACY
    return result


def _write_metrics(metrics_path: str, metrics: dict) -> None:
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


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


def _initialize_supportability_exclusion_metrics() -> dict:
    metrics = {}
    for metric_keys in SUPPORTABILITY_EXCLUSION_BUCKETS.values():
        metrics[metric_keys["count_key"]] = 0
        metrics[metric_keys["row_count_key"]] = 0
        metrics[metric_keys["codes_key"]] = []
    return metrics


def _build_supportability_exclusion_metrics(df: pd.DataFrame) -> dict:
    metrics = _initialize_supportability_exclusion_metrics()
    if df is None or df.empty:
        return metrics

    supportability_bucket = df["supportability_bucket"] if "supportability_bucket" in df.columns else pd.Series("", index=df.index, dtype="object")
    bond_codes = df["bond_code_raw"] if "bond_code_raw" in df.columns else pd.Series("", index=df.index, dtype="object")

    for bucket_name, metric_keys in SUPPORTABILITY_EXCLUSION_BUCKETS.items():
        bucket_mask = supportability_bucket.eq(bucket_name)
        filtered_codes = _extract_sorted_unique_codes(bond_codes.loc[bucket_mask])
        metrics[metric_keys["count_key"]] = len(filtered_codes)
        metrics[metric_keys["row_count_key"]] = int(bucket_mask.sum())
        metrics[metric_keys["codes_key"]] = filtered_codes

    return metrics


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


def _build_candidate_summary_metrics(df: pd.DataFrame) -> dict:
    row_count = int(len(df))
    if row_count == 0:
        return {
            "row_count": 0,
            "underlying_ticker_nonnull_ratio": 0.0,
            "premium_rate_nonzero_ratio": 0.0,
            "premium_rate_zero_ratio": 0.0,
            "is_st_true_count": 0,
            "is_redeemed_true_count": 0,
        }

    return {
        "row_count": row_count,
        "underlying_ticker_nonnull_ratio": float(df["underlying_ticker"].notna().mean()),
        "premium_rate_nonzero_ratio": float((df["premium_rate"] != 0).mean()),
        "premium_rate_zero_ratio": float((df["premium_rate"] == 0).mean()),
        "is_st_true_count": int(df["is_st"].sum()),
        "is_redeemed_true_count": int(df["is_redeemed"].sum()),
    }


def _promote_exclusion_only_metrics(tmp_metrics_path: str, metrics_path: str) -> None:
    metrics_bak_path = metrics_path + ".bak"
    metrics_backed_up = False
    metrics_existed = os.path.exists(metrics_path)

    try:
        if metrics_existed:
            os.replace(metrics_path, metrics_bak_path)
            metrics_backed_up = True

        os.replace(tmp_metrics_path, metrics_path)
    except Exception:
        if metrics_backed_up:
            os.replace(metrics_bak_path, metrics_path)
        elif not metrics_existed and os.path.exists(metrics_path):
            os.remove(metrics_path)

        if os.path.exists(tmp_metrics_path):
            os.remove(tmp_metrics_path)

        print("[DataPromotionRollback] Exclusion-only metrics promotion failed. Canonical dataset remains unchanged.")
        import sys

        sys.exit(1)


def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    output_path = DATA_PATH
    bak_path = output_path + ".bak"
    metrics_path = METRICS_PATH

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    pipeline = StagedPipeline([
        SourceAcquisitionStage(start_date, end_date),
        SupportabilityStage(start_date),
    ])

    stage_results = pipeline.run(stop_on_failure=True)

    if stage_results["source_coverage"]["status"] == "FAIL":
        message = stage_results["source_coverage"]["message"]
        if "Missing JQDATA_USER or JQDATA_PWD" in message:
            raise ValueError(message)
        if stage_results["source_coverage"]["failure_type"] == "SOURCE_AUTH_FAILURE":
            raise RuntimeError(message)
        else:
            raise ValueError(message)

    if stage_results["supportability_summary"]["status"] == "FAIL":
        raise ValueError(stage_results["supportability_summary"]["message"])

    df = pipeline.context["df"]
    df_bonds_info = pipeline.context["df_bonds_info"]
    bond_to_stock = _build_underlying_mapping(df_bonds_info)
    bond_to_delist = _build_delist_mapping(df_bonds_info)

    supportability_metrics = _build_supportability_exclusion_metrics(df)

    df = df[df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()

    premium_rate_metrics = {
        "premium_rate_source_row_count": 0,
        "premium_rate_joined_row_count": 0,
        "premium_rate_join_coverage_ratio": 0.0,
        "is_redeemed_missing_delist_count": 0,
    }
    exclusion_only_window = False

    if df.empty:
        exclusion_only_window = True
        df = _build_empty_canonical_cb_frame()
    else:
        df["underlying_ticker"] = df["bond_code_raw"].map(bond_to_stock)
        if df["underlying_ticker"].isna().any():
            raise ValueError(SUPPORTABILITY_REGRESSION_ERROR)

        raw_codes = [code for code in df["bond_code_raw"].dropna().astype(str).unique().tolist() if code]
        if raw_codes:
            q = jqdatasdk.query(jqdatasdk.bond.CONBOND_DAILY_CONVERT).filter(
                jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_(raw_codes),
                jqdatasdk.bond.CONBOND_DAILY_CONVERT.date >= start_date,
                jqdatasdk.bond.CONBOND_DAILY_CONVERT.date <= end_date,
            )
            df_premium_raw = jqdatasdk.bond.run_query(q)
            df_premium = _normalize_premium_source(df_premium_raw)
            premium_rate_metrics["premium_rate_source_row_count"] = int(len(df_premium))

            if not df_premium.empty:
                df = pd.merge(df, df_premium, on=["date", "bond_code_raw", "bond_exchange_code"], how="left")
            else:
                df["premium_rate"] = float("nan")
        else:
            df["premium_rate"] = float("nan")

        premium_rate_metrics["premium_rate_joined_row_count"] = int(df["premium_rate"].notna().sum())
        total_price_rows = int(len(df))
        premium_rate_metrics["premium_rate_join_coverage_ratio"] = (
            premium_rate_metrics["premium_rate_joined_row_count"] / total_price_rows if total_price_rows else 0.0
        )

        underlying_tickers = [
            ticker for ticker in df["underlying_ticker"].dropna().astype(str).unique().tolist() if ticker
        ]
        if underlying_tickers:
            df_st = jqdatasdk.get_extras("is_st", underlying_tickers, start_date=start_date, end_date=end_date)
            st_long = df_st.stack().reset_index()
            st_long.columns = ["date", "underlying_ticker", "is_st"]
            st_long["date"] = pd.to_datetime(st_long["date"])

            df = pd.merge(df, st_long, on=["date", "underlying_ticker"], how="left")

        if "is_st" not in df.columns or df["is_st"].isna().any():
            raise ValueError("Missing is_st for some records")

        df["delist_Date"] = pd.to_datetime(df["bond_code_raw"].map(bond_to_delist), errors="coerce")
        premium_rate_metrics["is_redeemed_missing_delist_count"] = int(df["delist_Date"].isna().sum())
        # The first deterministic redemption contract is intentionally narrow:
        # `delist_Date` is the only decision field, while `maturity_date`, `last_cash_date`,
        # and `convert_end_date` remain fallback informational fields for observability only.
        # When `delist_Date` is missing, AMS must keep `is_redeemed=False` instead of guessing.
        df["is_redeemed"] = df["delist_Date"].notna() & (df["date"] >= df["delist_Date"])
        if df["is_redeemed"].isna().any():
            raise ValueError("Missing is_redeemed for some records")

        num_redeemed = df["is_redeemed"].sum()
        print(f"Total redeemed records marked: {num_redeemed}")

        if "premium_rate" not in df.columns or df["premium_rate"].isna().any():
            raise ValueError("Missing premium_rate for some records")
        df["double_low"] = df["close"] + df["premium_rate"] * 100

        df = df[CANONICAL_CB_COLUMNS]

    metrics_bak_path = metrics_path + ".bak"
    tmp_metrics_path = metrics_path + ".tmp"
    
    import datetime
    premium_rate_metrics.update({
        **_build_candidate_summary_metrics(df),
        **supportability_metrics,
        "generated_at": datetime.datetime.now().isoformat(),
        "source_lineage": "jqdata_sync_cb"
    })

    _write_metrics(tmp_metrics_path, premium_rate_metrics)

    if exclusion_only_window:
        _promote_exclusion_only_metrics(tmp_metrics_path, metrics_path)
        print(
            "[ExclusionOnlyWindow] No supportable bonds survived; metrics updated and canonical dataset remains unchanged."
        )
        return

    from ams.validators.cb_data_validator import CBDataValidator, DatasetSemanticValidator

    validator_l1 = CBDataValidator()
    validator_l2 = DatasetSemanticValidator()
    tmp_path = output_path + ".tmp"

    df.to_csv(tmp_path, index=False)

    df_to_val = pd.read_csv(tmp_path)
    df_to_val["ticker"] = df_to_val["ticker"].astype(str)
    df_to_val["close"] = df_to_val["close"].astype(float)
    df_to_val["premium_rate"] = df_to_val["premium_rate"].astype(float)
    df_to_val["is_st"] = df_to_val["is_st"].astype(bool)
    df_to_val["is_redeemed"] = df_to_val["is_redeemed"].astype(bool)

    validation_passed = False
    try:
        val_l1 = validator_l1.validate_dataframe(df_to_val)
        val_l2 = validator_l2.validate_dataframe(df_to_val)
        validation_passed = val_l1 and val_l2
    except Exception as e:
        print(e)
        validation_passed = False

    import sys
    if validation_passed:
        canonical_backed_up = False
        metrics_backed_up = False
        canonical_existed = os.path.exists(output_path)
        metrics_existed = os.path.exists(metrics_path)
        try:
            if canonical_existed:
                os.replace(output_path, bak_path)
                canonical_backed_up = True
            if metrics_existed:
                os.replace(metrics_path, metrics_bak_path)
                metrics_backed_up = True
            
            os.replace(tmp_path, output_path)
            os.replace(tmp_metrics_path, metrics_path)
            print(f"Successfully synced data to {output_path}")
        except Exception as e:
            if canonical_backed_up:
                os.replace(bak_path, output_path)
            elif not canonical_existed and os.path.exists(output_path):
                os.remove(output_path)
                
            if metrics_backed_up:
                os.replace(metrics_bak_path, metrics_path)
            elif not metrics_existed and os.path.exists(metrics_path):
                os.remove(metrics_path)
                
            print("[DataPromotionRollback] Atomic promotion failed. Canonical dataset restored from backup.")
            sys.exit(1)
    else:
        print("[DataPromotionBlocked] Candidate research dataset failed validation. Canonical dataset remains unchanged.")
        sys.exit(1)


if __name__ == "__main__":
    sync_cb_data()
