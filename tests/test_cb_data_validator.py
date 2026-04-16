import os
import pandas as pd
import pytest
from ams.validators.cb_data_validator import CBDataValidator

def test_validator_with_perfect_dataframe():
    df = pd.DataFrame({
        "ticker": ["110001", "110002"],
        "date": ["2023-01-01", "2023-01-02"],
        "close": [105.0, 110.0],
        "premium_rate": [15.0, 20.0],
        "is_st": [False, False],
        "is_redeemed": [False, False]
    })
    validator = CBDataValidator()
    assert validator.validate_dataframe(df) is True

def test_validator_catches_nan_premium_rate(capsys):
    df = pd.DataFrame({
        "ticker": ["110001"],
        "date": ["2023-01-01"],
        "close": [105.0],
        "premium_rate": [float("nan")],
        "is_st": [False],
        "is_redeemed": [False]
    })
    validator = CBDataValidator()
    assert validator.validate_dataframe(df) is False
    captured = capsys.readouterr()
    assert "[DataContractViolation] Validation failed due to SchemaError:" in captured.out

def test_validator_catches_invalid_close_price():
    df = pd.DataFrame({
        "ticker": ["110001"],
        "date": ["2023-01-01"],
        "close": [-1.0],
        "premium_rate": [15.0],
        "is_st": [False],
        "is_redeemed": [False]
    })
    validator = CBDataValidator()
    assert validator.validate_dataframe(df) is False

def test_validator_catches_missing_columns():
    df = pd.DataFrame({
        "ticker": ["110001"],
        "date": ["2023-01-01"],
        "close": [105.0],
        "premium_rate": [15.0],
        "is_redeemed": [False]
    })
    validator = CBDataValidator()
    assert validator.validate_dataframe(df) is False

def test_requirements_file_exists():
    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    assert os.path.exists(req_path)
    with open(req_path, "r") as f:
        content = f.read()
    assert "pandera>=0.20.0" in content
