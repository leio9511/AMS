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

def test_cli_valid_csv(tmp_path):
    import subprocess
    import sys
    csv_file = tmp_path / "valid.csv"
    df = pd.DataFrame({
        "ticker": ["110001"],
        "date": ["2023-01-01"],
        "close": [105.0],
        "premium_rate": [15.0],
        "is_st": [False],
        "is_redeemed": [False]
    })
    df.to_csv(csv_file, index=False)
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "ams", "validators", "cb_data_validator.py")
    result = subprocess.run([sys.executable, script_path, "--csv", str(csv_file)], capture_output=True, text=True)
    assert result.returncode == 0

def test_cli_invalid_csv(tmp_path):
    import subprocess
    import sys
    csv_file = tmp_path / "invalid.csv"
    df = pd.DataFrame({
        "ticker": ["110001"],
        "date": ["2023-01-01"],
        "close": [105.0],
        "premium_rate": [float("nan")],
        "is_st": [False],
        "is_redeemed": [False]
    })
    df.to_csv(csv_file, index=False)
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "ams", "validators", "cb_data_validator.py")
    result = subprocess.run([sys.executable, script_path, "--csv", str(csv_file)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "[DataContractViolation] Validation failed due to SchemaError:" in result.stdout

from ams.validators.cb_data_validator import DatasetSemanticValidator, DataSemanticViolation, DataDriftViolation
import json

def test_semantic_validation_success(tmp_path):
    baseline_file = tmp_path / "baseline.json"
    baseline_data = {
        "row_count": 50000,
        "premium_rate_nonzero_ratio": 0.98,
        "is_st_true_count": 2,
        "is_redeemed_true_count": 2
    }
    baseline_file.write_text(json.dumps(baseline_data))

    df = pd.DataFrame({
        "underlying_ticker": ["000001"] * 50000,
        "premium_rate": [0.1] * 49000 + [0.0] * 1000,
        "is_st": [True] * 2 + [False] * 49998,
        "is_redeemed": [True] * 2 + [False] * 49998
    })

    validator = DatasetSemanticValidator(baseline_path=str(baseline_file))
    assert validator.validate_dataframe(df) is True

def test_semantic_validation_collapsed_premium(tmp_path):
    baseline_file = tmp_path / "baseline.json"
    baseline_data = {
        "row_count": 50000,
        "premium_rate_nonzero_ratio": 0.98,
        "is_st_true_count": 2,
        "is_redeemed_true_count": 2
    }
    baseline_file.write_text(json.dumps(baseline_data))
    
    # ratio of nonzero is < 0.95
    df = pd.DataFrame({
        "underlying_ticker": ["000001"] * 50000,
        "premium_rate": [0.1] * 40000 + [0.0] * 10000,
        "is_st": [True] * 2 + [False] * 49998,
        "is_redeemed": [True] * 2 + [False] * 49998
    })
    
    validator = DatasetSemanticValidator(baseline_path=str(baseline_file))
    with pytest.raises(DataSemanticViolation) as excinfo:
        validator.validate_dataframe(df)
    assert "[DataSemanticViolation] premium_rate_nonzero_ratio below minimum threshold." in str(excinfo.value)

def test_semantic_validation_zero_st_events(tmp_path):
    baseline_file = tmp_path / "baseline.json"
    baseline_data = {
        "row_count": 50000,
        "premium_rate_nonzero_ratio": 0.98,
        "is_st_true_count": 2,
        "is_redeemed_true_count": 2
    }
    baseline_file.write_text(json.dumps(baseline_data))
    
    df = pd.DataFrame({
        "underlying_ticker": ["000001"] * 50000,
        "premium_rate": [0.1] * 49000 + [0.0] * 1000,
        "is_st": [False] * 50000,
        "is_redeemed": [True] * 2 + [False] * 49998
    })
    
    validator = DatasetSemanticValidator(baseline_path=str(baseline_file))
    with pytest.raises(DataSemanticViolation) as excinfo:
        validator.validate_dataframe(df)
    assert "[DataSemanticViolation] is_st_true_count below minimum threshold." in str(excinfo.value)

def test_semantic_validation_drift_violation(tmp_path):
    baseline_file = tmp_path / "baseline.json"
    # mock a baseline with 100k rows
    baseline_data = {
        "row_count": 100000,
        "premium_rate_nonzero_ratio": 0.98,
        "is_st_true_count": 2,
        "is_redeemed_true_count": 2
    }
    baseline_file.write_text(json.dumps(baseline_data))
    
    # provide a dataframe with 50k rows, which is a drop > 20%
    df = pd.DataFrame({
        "underlying_ticker": ["000001"] * 50000,
        "premium_rate": [0.1] * 49000 + [0.0] * 1000,
        "is_st": [True] * 2 + [False] * 49998,
        "is_redeemed": [True] * 2 + [False] * 49998
    })
    
    validator = DatasetSemanticValidator(baseline_path=str(baseline_file))
    with pytest.raises(DataDriftViolation) as excinfo:
        validator.validate_dataframe(df)
    assert "[DataDriftViolation] candidate dataset drift exceeded baseline guardrail." in str(excinfo.value)
