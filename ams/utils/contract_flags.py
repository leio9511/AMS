from __future__ import annotations

import numpy as np
import pandas as pd


TRUTHY_STRING_FLAGS = {"true", "1"}
FALSY_STRING_FLAGS = {"false", "0"}


def normalize_contract_flag_value(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    if isinstance(value, (int, np.integer)) and value in (0, 1):
        return bool(value)

    if isinstance(value, (float, np.floating)) and value in (0.0, 1.0):
        return bool(int(value))

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUTHY_STRING_FLAGS:
            return True
        if lowered in FALSY_STRING_FLAGS:
            return False

    return pd.NA



def _invalid_contract_flag_values(series: pd.Series, invalid_mask: pd.Series) -> list[str]:
    return sorted({str(value) for value in series.loc[invalid_mask].tolist()})



def normalize_contract_flag_series(
    series: pd.Series,
    *,
    null_default: bool | None,
    invalid: str = "preserve",
    field_name: str = "contract flag",
) -> pd.Series:
    normalized = series.map(
        lambda value: pd.NA if pd.isna(value) else normalize_contract_flag_value(value)
    )
    invalid_mask = series.notna() & normalized.isna()
    if invalid_mask.any():
        if invalid == "preserve":
            return series
        if invalid == "raise":
            invalid_values = _invalid_contract_flag_values(series, invalid_mask)
            raise ValueError(
                f"{field_name} contains invalid non-boolean-like values: {invalid_values}"
            )
        raise ValueError(f"Unsupported invalid handling mode: {invalid}")

    if null_default is None:
        if normalized.isna().any():
            return normalized.astype("boolean")
        return normalized.astype(bool)

    normalized = normalized.where(~normalized.isna(), null_default)
    return normalized.astype(bool)



def build_contract_flag_exclusion_mask(
    series: pd.Series,
    *,
    null_default: bool,
    invalid_default: bool,
) -> pd.Series:
    normalized = series.map(
        lambda value: pd.NA if pd.isna(value) else normalize_contract_flag_value(value)
    )
    invalid_mask = series.notna() & normalized.isna()
    normalized = normalized.where(~normalized.isna(), null_default)
    if invalid_mask.any():
        normalized.loc[invalid_mask] = invalid_default
    return normalized.astype(bool)
