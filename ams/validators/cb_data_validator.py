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
