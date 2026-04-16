import pandera as pa
import pandas as pd

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
    
    # Cast types for pandas since read_csv might infer incorrectly
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
