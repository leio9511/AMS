import pandera as pa
import pandas as pd
import json
import os

cb_schema = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str, nullable=False),
        "date": pa.Column(nullable=False),
        "close": pa.Column(float, checks=pa.Check(lambda s: s > 0), nullable=False),
        "premium_rate": pa.Column(
            float, checks=pa.Check(lambda s: (s >= -10.0) & (s <= 100.0)), nullable=False
        ),
        "is_st": pa.Column(bool, nullable=False),
        "is_redeemed": pa.Column(bool, nullable=False),
    }
)

class CBDataValidator:
    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        try:
            cb_schema.validate(df)
            return True
        except pa.errors.SchemaError as e:
            print(f"[DataContractViolation] Validation failed due to SchemaError: {e}")
            return False

class DataSemanticViolation(Exception):
    pass

class DataDriftViolation(Exception):
    pass

class DatasetSemanticValidator:
    def __init__(self, baseline_path="/root/projects/AMS/data/cb_history_factors.metrics.json"):
        self.baseline_path = baseline_path
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

        if os.path.exists(self.baseline_path):
            try:
                with open(self.baseline_path, "r") as f:
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
    
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str)
    if "is_st" in df.columns:
        df["is_st"] = df["is_st"].astype(bool)
    if "is_redeemed" in df.columns:
        df["is_redeemed"] = df["is_redeemed"].astype(bool)

    validator = CBDataValidator()
    if validator.validate_dataframe(df):
        sys.exit(0)
    else:
        sys.exit(1)
