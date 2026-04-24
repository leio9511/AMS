import json
import os

import jqdatasdk
import pandas as pd


METRICS_PATH = "data/cb_history_factors.metrics.json"
LEGACY_UNDERLYING_SOURCE_FATAL = (
    "[FATAL] Invalid underlying-ticker source contract: get_security_info(ticker).parent "
    "is not valid for AMS convertible bonds."
)
LEGACY_REDEMPTION_SOURCE_FATAL = (
    "[FATAL] Invalid redemption source contract: finance.CCB_CALL is not a valid "
    "JQData table for AMS convertible-bond lifecycle semantics."
)
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


def _build_underlying_mapping(df_bonds_info: pd.DataFrame) -> dict:
    if df_bonds_info is None or df_bonds_info.empty:
        return {}
    if "code" not in df_bonds_info.columns or "company_code" not in df_bonds_info.columns:
        return {}

    mapping_df = df_bonds_info[["code", "company_code"]].dropna(subset=["code", "company_code"])
    if mapping_df.empty:
        return {}

    mapping_df = mapping_df.drop_duplicates(subset=["code"], keep="last")
    return mapping_df.set_index("code")["company_code"].to_dict()


def _build_delist_mapping(df_bonds_info: pd.DataFrame) -> dict:
    contract = REDEMPTION_SOURCE_CONTRACT
    if df_bonds_info is None or df_bonds_info.empty:
        return {}
    if "code" not in df_bonds_info.columns or contract["primary_field"] not in df_bonds_info.columns:
        return {}

    mapping_df = df_bonds_info[["code", contract["primary_field"]]].copy()
    mapping_df[contract["primary_field"]] = pd.to_datetime(mapping_df[contract["primary_field"]], errors="coerce")
    mapping_df = mapping_df.drop_duplicates(subset=["code"], keep="last")
    return mapping_df.set_index("code")[contract["primary_field"]].to_dict()


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


def _write_metrics(metrics_path: str, metrics: dict) -> None:
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    output_path = "data/cb_history_factors.csv"
    bak_path = "data/cb_history_factors.csv.bak"
    metrics_path = METRICS_PATH

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        import shutil

        shutil.copy2(output_path, bak_path)

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

    df["underlying_ticker"] = df["ticker"].map(bond_to_stock)
    df = _build_bond_key_columns(df, ticker_col="ticker")

    premium_rate_metrics = {
        "premium_rate_source_row_count": 0,
        "premium_rate_joined_row_count": 0,
        "premium_rate_join_coverage_ratio": 0.0,
        "is_redeemed_missing_delist_count": 0,
    }

    raw_codes = [code for code in df["bond_code_raw"].dropna().astype(str).unique().tolist() if code]
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
        df["premium_rate"] = 0.0

    premium_rate_metrics["premium_rate_joined_row_count"] = int(df["premium_rate"].notna().sum())
    total_price_rows = int(len(df))
    premium_rate_metrics["premium_rate_join_coverage_ratio"] = (
        premium_rate_metrics["premium_rate_joined_row_count"] / total_price_rows if total_price_rows else 0.0
    )

    underlying_tickers = [ticker for ticker in df["underlying_ticker"].dropna().astype(str).unique().tolist() if ticker]
    if underlying_tickers:
        df_st = jqdatasdk.get_extras("is_st", underlying_tickers, start_date=start_date, end_date=end_date)
        st_long = df_st.stack().reset_index()
        st_long.columns = ["date", "underlying_ticker", "is_st"]
        st_long["date"] = pd.to_datetime(st_long["date"])

        df = pd.merge(df, st_long, on=["date", "underlying_ticker"], how="left")

    df["is_st"] = df["is_st"].fillna(False)

    df["delist_Date"] = pd.to_datetime(df["ticker"].map(bond_to_delist), errors="coerce")
    premium_rate_metrics["is_redeemed_missing_delist_count"] = int(df["delist_Date"].isna().sum())
    # The first deterministic redemption contract is intentionally narrow:
    # `delist_Date` is the only decision field, while `maturity_date`, `last_cash_date`,
    # and `convert_end_date` remain fallback informational fields for observability only.
    # When `delist_Date` is missing, AMS must keep `is_redeemed=False` instead of guessing.
    df["is_redeemed"] = df["delist_Date"].notna() & (df["date"] >= df["delist_Date"])

    num_redeemed = df["is_redeemed"].sum()
    print(f"Total redeemed records marked: {num_redeemed}")

    df["premium_rate"] = df["premium_rate"].fillna(0.0)
    df["double_low"] = df["close"] + df["premium_rate"] * 100

    df = df[[
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
    ]]

    _write_metrics(metrics_path, premium_rate_metrics)

    from ams.validators.cb_data_validator import CBDataValidator

    validator = CBDataValidator()
    tmp_path = "data/cb_history_factors.csv.tmp"

    df.to_csv(tmp_path, index=False)

    df_to_val = pd.read_csv(tmp_path)
    df_to_val["ticker"] = df_to_val["ticker"].astype(str)
    df_to_val["is_st"] = df_to_val["is_st"].astype(bool)
    df_to_val["is_redeemed"] = df_to_val["is_redeemed"].astype(bool)

    if validator.validate_dataframe(df_to_val):
        os.replace(tmp_path, output_path)
        print(f"Successfully synced data to {output_path}")
    else:
        print(f"[DataContractViolation] Validation failed for {tmp_path}, keeping old file.")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    sync_cb_data()
