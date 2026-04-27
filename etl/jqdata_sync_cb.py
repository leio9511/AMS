import json
import os

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

    user = os.environ.get("JQDATA_USER")
    pwd = os.environ.get("JQDATA_PWD")

    if not user or not pwd:
        raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")

    try:
        jqdatasdk.auth(user, pwd)
    except Exception as e:
        raise RuntimeError(f"JQData auth failed: {e}")

    df_bonds_info = jqdatasdk.bond.run_query(jqdatasdk.query(jqdatasdk.bond.CONBOND_BASIC_INFO))
    bond_to_stock = _build_underlying_mapping(df_bonds_info)
    bond_to_delist = _build_delist_mapping(df_bonds_info)

    df_all_bonds = jqdatasdk.get_all_securities(["conbond"])
    tickers = df_all_bonds.index.tolist()

    df_price = jqdatasdk.get_price(
        tickers,
        start_date=start_date,
        end_date=end_date,
        frequency="daily",
        fields=["open", "high", "low", "close", "volume"],
    )
    if df_price.empty:
        raise ValueError("No price data found for the given range")

    df = df_price.reset_index()
    df.rename(columns={"time": "date", "code": "ticker"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])

    df = _build_bond_key_columns(df, ticker_col="ticker")
    df = _classify_supportability(df, df_bonds_info, start_date)

    supportability_metrics = _build_supportability_exclusion_metrics(df)
    unexpected_contract_regression_mask = df["supportability_bucket"].eq(
        SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION
    )

    if unexpected_contract_regression_mask.any():
        raise ValueError(SUPPORTABILITY_REGRESSION_ERROR)

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
