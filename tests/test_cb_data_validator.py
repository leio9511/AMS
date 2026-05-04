import os
import pandas as pd
import pytest
from ams.validators.cb_data_validator import CBDataValidator, normalize_core_validator_frame

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

def test_validator_catches_nan_close(capsys):
    df = pd.DataFrame({
        "ticker": ["110001"],
        "date": ["2023-01-01"],
        "close": [float("nan")],
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


def test_core_validator_only_checks_prd_required_columns_and_close_semantics():
    validator = CBDataValidator()
    valid_core = normalize_core_validator_frame(
        pd.DataFrame(
            {
                "ticker": ["110001.XSHG", "110002.XSHG"],
                "date": [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-06")],
                "close": [100.0, 101.0],
                "is_st": [False, False],
                "is_redeemed": [False, False],
            }
        )
    )

    assert validator.validate_dataframe(valid_core) is True

    invalid_cases = [
        normalize_core_validator_frame(valid_core.assign(ticker=[None, "110002.XSHG"])),
        normalize_core_validator_frame(valid_core.assign(date=[pd.NaT, pd.Timestamp("2025-01-06")])),
        normalize_core_validator_frame(valid_core.assign(close=[0.0, 101.0])),
        normalize_core_validator_frame(valid_core.assign(close=[-1.0, 101.0])),
        normalize_core_validator_frame(valid_core.assign(is_st=["bad-bool", False])),
        normalize_core_validator_frame(valid_core.assign(is_redeemed=[False, None])),
    ]
    for invalid_df in invalid_cases:
        assert validator.validate_dataframe(invalid_df) is False

    with_non_contract_enrichment_gap = valid_core.assign(
        premium_rate=[float("nan"), float("nan")],
        double_low=[float("nan"), float("nan")],
        underlying_ticker=[None, None],
    )
    assert validator.validate_dataframe(with_non_contract_enrichment_gap) is True



def test_normalize_core_validator_frame_fills_is_st_nulls_with_false_for_core_schema():
    raw = pd.DataFrame(
        {
            "ticker": ["110001.XSHG", "110002.XSHG", "110003.XSHG", "110004.XSHG"],
            "date": [pd.Timestamp("2025-01-06")] * 4,
            "close": [100.0, 101.0, 102.0, 103.0],
            "is_st": [False, None, pd.NA, 1],
            "is_redeemed": [False, False, False, False],
        }
    )

    normalized = normalize_core_validator_frame(raw)

    assert normalized["is_st"].dtype == bool
    assert normalized["is_st"].tolist() == [False, False, False, True]



def test_normalize_core_validator_frame_keeps_is_redeemed_nullable_behavior_unchanged():
    raw = pd.DataFrame(
        {
            "ticker": ["110001.XSHG", "110002.XSHG", "110003.XSHG", "110004.XSHG"],
            "date": [pd.Timestamp("2025-01-06")] * 4,
            "close": [100.0, 101.0, 102.0, 103.0],
            "is_st": [False, False, True, False],
            "is_redeemed": [False, None, pd.NA, 1],
        }
    )

    normalized = normalize_core_validator_frame(raw)

    assert str(normalized["is_redeemed"].dtype) == "boolean"
    assert normalized.loc[0, "is_redeemed"] == False
    assert normalized.loc[1, "is_redeemed"] is pd.NA
    assert normalized.loc[2, "is_redeemed"] is pd.NA
    assert normalized.loc[3, "is_redeemed"] == True



def test_core_validator_accepts_is_st_source_gap_after_field_specific_normalization():
    validator = CBDataValidator()
    normalized = normalize_core_validator_frame(
        pd.DataFrame(
            {
                "ticker": ["110001.XSHG", "110002.XSHG", "110003.XSHG"],
                "date": [pd.Timestamp("2025-01-06")] * 3,
                "close": [100.0, 101.0, 102.0],
                "is_st": [False, None, pd.NA],
                "is_redeemed": [False, False, False],
            }
        )
    )

    assert validator.validate_dataframe(normalized) is True
    assert "non-nullable series 'is_st' contains null values:" not in validator.last_error_message



def test_core_validator_still_rejects_nullable_is_redeemed_contract_violation():
    validator = CBDataValidator()
    normalized = normalize_core_validator_frame(
        pd.DataFrame(
            {
                "ticker": ["110001.XSHG", "110002.XSHG"],
                "date": [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-06")],
                "close": [100.0, 101.0],
                "is_st": [False, None],
                "is_redeemed": [False, None],
            }
        )
    )

    assert validator.validate_dataframe(normalized) is False
    assert "is_redeemed" in validator.last_error_message



def test_normalize_core_validator_frame_returns_schema_compatible_core_dtypes():
    raw = pd.DataFrame(
        {
            "ticker": pd.Series(["110001.XSHG", None], dtype=object),
            "date": [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-07")],
            "close": ["100.5", "bad-close"],
            "is_st": [0, 1],
            "is_redeemed": [False, None],
        }
    )

    normalized = normalize_core_validator_frame(raw)

    assert str(normalized["ticker"].dtype) == "string"
    assert getattr(normalized["ticker"].dtype, "storage", None) == "pyarrow"
    assert normalized.loc[0, "ticker"] == "110001.XSHG"
    assert normalized.loc[1, "ticker"] is pd.NA

    assert normalized["close"].dtype.kind == "f"
    assert normalized.loc[0, "close"] == pytest.approx(100.5)
    assert pd.isna(normalized.loc[1, "close"])

    assert normalized["is_st"].dtype == bool
    assert normalized["is_st"].tolist() == [False, True]

    assert str(normalized["is_redeemed"].dtype) == "boolean"
    assert normalized.loc[0, "is_redeemed"] == False
    assert normalized.loc[1, "is_redeemed"] is pd.NA

    assert raw["ticker"].dtype == object

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
        "close": [float("nan")],
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

@pytest.mark.legacy_dataset_semantic
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

@pytest.mark.legacy_dataset_semantic
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

@pytest.mark.legacy_dataset_semantic
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

@pytest.mark.legacy_dataset_semantic
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

from ams.validators.cb_data_validator import EnrichmentValidator

def test_enrichment_validator_double_low_canonical():
    df = pd.DataFrame({
        "close": [100.0, 110.0],
        "premium_rate": [0.10, 0.20],
        "double_low": [110.0, 131.0] # 110 + 0.20*100 = 130.0 != 131.0
    })
    validator = EnrichmentValidator()
    status, msg = validator.validate_dataframe(df)
    assert status == "FAIL"
    assert "VALIDATOR_SEMANTIC_FAILURE" in msg

def test_enrichment_validator_reports_degradation():
    df = pd.DataFrame({
        "close": [100.0] * 20,
        "premium_rate": [0.10] * 10 + [float('nan')] * 10,
        "double_low": [110.0] * 10 + [float('nan')] * 10
    })
    validator = EnrichmentValidator()
    status, msg = validator.validate_dataframe(df)
    assert status == "DEGRADED"
    assert "High missing ratio on premium" in msg


def test_enrichment_validator_only_targets_enrichment_universe_semantics():
    validator = EnrichmentValidator()
    compliant_enrichment_rows = pd.DataFrame(
        {
            "close": [100.0, 101.0],
            "premium_rate": [0.10, 0.12],
            "double_low": [110.0, 113.0],
            "ticker": [None, None],
            "is_st": [None, None],
            "is_redeemed": [None, None],
        }
    )

    status, msg = validator.validate_dataframe(compliant_enrichment_rows)
    assert status == "PASS"
    assert msg == ""

    degraded_rows = compliant_enrichment_rows.copy()
    degraded_rows.loc[0, "premium_rate"] = float("nan")
    status, msg = validator.validate_dataframe(degraded_rows)
    assert status == "DEGRADED"
    assert "High missing ratio on premium" in msg

    failing_rows = compliant_enrichment_rows.copy()
    failing_rows.loc[0, "double_low"] = 999.0
    status, msg = validator.validate_dataframe(failing_rows)
    assert status == "FAIL"
    assert "double_low does not match canonical formula" in msg
