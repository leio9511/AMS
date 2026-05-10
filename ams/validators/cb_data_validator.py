import json
from pathlib import Path

import pandera as pa
import pandas as pd
import numpy as np

try:
    from ams.utils.path_resolver import resolve_mutable_data_path
except ModuleNotFoundError:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from ams.utils.path_resolver import resolve_mutable_data_path

cb_schema = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str, nullable=False),
        "date": pa.Column(nullable=False),
        "close": pa.Column(float, checks=pa.Check(lambda s: s > 0), nullable=False),
        "is_st": pa.Column(bool, nullable=False),
        "redeem_risk": pa.Column(bool, nullable=False),
        "is_redeemed": pa.Column(bool, nullable=False),
    }
)

CORE_VALIDATOR_TICKER_DTYPE = pd.StringDtype(storage="pyarrow")


def _normalize_contract_bool_value(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    if isinstance(value, (int, np.integer)) and value in (0, 1):
        return bool(value)

    if isinstance(value, (float, np.floating)) and value in (0.0, 1.0):
        return bool(int(value))

    return pd.NA


def _normalize_contract_bool_series(series: pd.Series) -> pd.Series:
    normalized = series.map(
        lambda value: pd.NA if pd.isna(value) else _normalize_contract_bool_value(value)
    )
    invalid_mask = series.notna() & normalized.isna()
    if invalid_mask.any():
        return series

    if normalized.isna().any():
        return normalized.astype("boolean")

    return normalized.astype(bool)


def _normalize_is_st_for_core_validator(series: pd.Series) -> pd.Series:
    """Normalize is_st for Stage-F core validation only.

    The shared contract bool helper intentionally preserves nulls as nullable
    booleans. Stage-F core validation treats ``is_st`` as an explicit
    field-specific exception: source-gap nulls are normalized to ``False`` for
    validator input only, while invalid non-boolean-like values are preserved so
    the schema validator still rejects them.
    """

    normalized = series.map(
        lambda value: False if pd.isna(value) else _normalize_contract_bool_value(value)
    )
    invalid_mask = series.notna() & normalized.isna()
    if invalid_mask.any():
        return series

    return normalized.astype(bool)


def normalize_core_validator_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()

    if "ticker" in normalized.columns:
        normalized["ticker"] = normalized["ticker"].astype(CORE_VALIDATOR_TICKER_DTYPE)

    if "close" in normalized.columns:
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")

    if "is_st" in normalized.columns:
        normalized["is_st"] = _normalize_is_st_for_core_validator(normalized["is_st"])

    if "redeem_risk" in normalized.columns:
        normalized["redeem_risk"] = normalized["redeem_risk"].map(
            lambda value: False if pd.isna(value) else _normalize_contract_bool_value(value)
        )
        invalid_mask = normalized["redeem_risk"].isna() & df["redeem_risk"].notna()
        if invalid_mask.any():
            normalized["redeem_risk"] = df["redeem_risk"]
        else:
            normalized["redeem_risk"] = normalized["redeem_risk"].astype(bool)

    if "is_redeemed" in normalized.columns:
        normalized["is_redeemed"] = _normalize_contract_bool_series(normalized["is_redeemed"])

    return normalized

class CBDataValidator:
    def __init__(self):
        self.last_error_message = ""

    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        self.last_error_message = ""
        try:
            normalized = normalize_core_validator_frame(df)
            cb_schema.validate(normalized)
            return True
        except pa.errors.SchemaError as e:
            self.last_error_message = str(e)
            print(f"[DataContractViolation] Validation failed due to SchemaError: {e}")
            return False

class DataSemanticViolation(Exception):
    pass

class DataDriftViolation(Exception):
    pass

class EnrichmentValidator:
    def validate_dataframe(self, df: pd.DataFrame) -> tuple[str, str]:
        if df.empty:
            return "PASS", ""

        if "premium_rate" not in df.columns:
            return "DEGRADED", "Missing premium_rate column"

        if "double_low" not in df.columns:
            return "DEGRADED", "Missing double_low column"

        valid_rows = df.dropna(subset=["double_low", "close", "premium_rate"])
        if not valid_rows.empty:
            expected_double_low = valid_rows["close"] + valid_rows["premium_rate"] * 100
            mismatched = (valid_rows["double_low"] - expected_double_low).abs() > 1e-4
            if mismatched.any():
                return "FAIL", "VALIDATOR_SEMANTIC_FAILURE: double_low does not match canonical formula"

        missing_ratio = df["premium_rate"].isna().mean()
        if missing_ratio > 0.05:
            return "DEGRADED", f"High missing ratio on premium: {missing_ratio:.2%}"

        return "PASS", ""

class DatasetSemanticValidator:
    """Legacy dataset-wide validator retained for backward-compatible direct callers.

    Stage F no longer invokes this class. The field-governed audit path is
    limited to the PRD validator contract: core checks in ``CBDataValidator``
    and enrichment checks in ``EnrichmentValidator``. The legacy semantic
    thresholds below intentionally remain available to older direct tests/tools
    until those callers are migrated.
    """

    DEFAULT_BASELINE_RELATIVE_PATH = "data/cb_history_factors.metrics.json"

    def __init__(self, baseline_path=None):
        if baseline_path is None:
            # Baseline schemas are located relative to the repository root
            ams_pkg_dir = Path(__file__).resolve().parent.parent
            self.baseline_path = str(ams_pkg_dir.parent / self.DEFAULT_BASELINE_RELATIVE_PATH)
        else:
            self.baseline_path = str(resolve_mutable_data_path(
                default_relative_path=self.DEFAULT_BASELINE_RELATIVE_PATH,
                cli_override=baseline_path,
            ).path)
        self.thresholds = {
            "row_count_min": 50000,
            "underlying_ticker_nonnull_ratio_min": 0.99,
            "premium_rate_nonzero_ratio_min": 0.95,
            "premium_rate_zero_ratio_max": 0.05,
            "is_st_true_count_min": 1,
            "is_redeemed_true_count_min": 1,
            "row_count_drop_ratio_max": 0.20,
            "premium_rate_nonzero_ratio_drop_max": 0.10
        }

    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        row_count = len(df)
        if row_count < self.thresholds["row_count_min"]:
            raise DataSemanticViolation("[DataSemanticViolation] row_count below minimum threshold.")

        if "underlying_ticker" in df.columns:
            underlying_ticker_nonnull_ratio = df["underlying_ticker"].notnull().mean()
        else:
            underlying_ticker_nonnull_ratio = 0.0
            
        if underlying_ticker_nonnull_ratio < self.thresholds["underlying_ticker_nonnull_ratio_min"]:
            raise DataSemanticViolation("[DataSemanticViolation] candidate dataset collapsed into default-value world.")

        premium_rate_nonzero_ratio = (df["premium_rate"] != 0.0).mean()
        premium_rate_zero_ratio = (df["premium_rate"] == 0.0).mean()
        is_st_true_count = df["is_st"].sum()
        is_redeemed_true_count = df["is_redeemed"].sum()

        if premium_rate_nonzero_ratio < self.thresholds["premium_rate_nonzero_ratio_min"]:
            raise DataSemanticViolation("[DataSemanticViolation] premium_rate_nonzero_ratio below minimum threshold.")
            
        if premium_rate_zero_ratio > self.thresholds["premium_rate_zero_ratio_max"]:
            raise DataSemanticViolation("[DataSemanticViolation] candidate dataset collapsed into default-value world.")
            
        if is_st_true_count < self.thresholds["is_st_true_count_min"]:
            raise DataSemanticViolation("[DataSemanticViolation] is_st_true_count below minimum threshold.")
            
        if is_redeemed_true_count < self.thresholds["is_redeemed_true_count_min"]:
            raise DataSemanticViolation("[DataSemanticViolation] is_redeemed_true_count below minimum threshold.")

        if (df["premium_rate"] == 0.0).all() or (~df["is_st"]).all() or (~df["is_redeemed"]).all():
            raise DataSemanticViolation("[DataSemanticViolation] candidate dataset collapsed into default-value world.")

        baseline_path = Path(self.baseline_path)
        if baseline_path.exists():
            try:
                with baseline_path.open("r") as f:
                    baseline = json.load(f)
                
                baseline_row_count = baseline.get("row_count", 0)
                if baseline_row_count > 0:
                    row_count_drop_ratio = (baseline_row_count - row_count) / baseline_row_count
                    if row_count_drop_ratio > self.thresholds["row_count_drop_ratio_max"]:
                        raise DataDriftViolation("[DataDriftViolation] candidate dataset drift exceeded baseline guardrail.")
                
                baseline_premium_nonzero = baseline.get("premium_rate_nonzero_ratio", 0.0)
                premium_nonzero_drop = baseline_premium_nonzero - premium_rate_nonzero_ratio
                if premium_nonzero_drop > self.thresholds["premium_rate_nonzero_ratio_drop_max"]:
                    raise DataDriftViolation("[DataDriftViolation] candidate dataset drift exceeded baseline guardrail.")
                    
                baseline_is_st = baseline.get("is_st_true_count", 0)
                if baseline_is_st > 0 and is_st_true_count == 0:
                    raise DataDriftViolation("[DataDriftViolation] candidate dataset drift exceeded baseline guardrail.")
                    
                baseline_is_redeemed = baseline.get("is_redeemed_true_count", 0)
                if baseline_is_redeemed > 0 and is_redeemed_true_count == 0:
                    raise DataDriftViolation("[DataDriftViolation] candidate dataset drift exceeded baseline guardrail.")
            except Exception as e:
                if isinstance(e, DataDriftViolation):
                    raise e
                pass

        return True

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Validate CB Data CSV")
    parser.add_argument("--csv", required=True, help="Path to the CSV file to validate")
    args = parser.parse_args()

    try:
        df = pd.read_csv(args.csv)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    df = normalize_core_validator_frame(df)

    validator = CBDataValidator()
    if validator.validate_dataframe(df):
        sys.exit(0)
    else:
        sys.exit(1)
