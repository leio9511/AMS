import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from unittest.mock import MagicMock, patch

from etl.cb_etl_pipeline import (
    CBETLPipeline,
    SUPPORTABILITY_BUCKET_SUPPORTABLE,
    _normalize_core_validator_input,
)
from ams.validators.cb_data_validator import CBDataValidator


def _contract_valid_pipeline() -> CBETLPipeline:
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG", "110002.XSHG"],
            "date": [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-06")],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000, 1200],
            "premium_rate": [0.10, 0.12],
            "double_low": [110.5, 113.5],
            "underlying_ticker": ["600001.XSHG", "600002.XSHG"],
            "is_st": [False, False],
            "is_redeemed": [False, False],
            "bond_code_raw": ["110001", "110002"],
            "bond_exchange_code": ["XSHG", "XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE, SUPPORTABILITY_BUCKET_SUPPORTABLE],
        }
    )
    pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["supportability_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "supportable_row_count": 2,
            "supportable_unique_bond_count": 2,
        }
    )
    pipeline.results["premium_join_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "premium_joined_row_count": 2,
            "premium_joined_unique_bond_count": 2,
            "missing_premium_row_count": 0,
            "missing_premium_unique_bond_count": 0,
            "missing_premium_ratio": 0.0,
            "premium_missing_ratio_against_active_universe": 0.0,
            "rate_limited_enrichment": False,
            "permission_degraded_enrichment": False,
        }
    )
    pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["active_universe_summary"].update(
        {
            "core_price_row_count_before_filter": 2,
            "core_price_row_count_after_filter": 2,
            "all_null_ohlcv_row_count_filtered": 0,
            "core_universe_row_count": 2,
            "core_universe_unique_bond_count": 2,
            "active_bond_universe_count": 2,
            "enrichment_target_row_count": 2,
            "enrichment_target_unique_bond_count": 2,
        }
    )
    return pipeline


def test_stage_f_normalizes_ticker_dtype_before_core_validator():
    pipeline = _contract_valid_pipeline()
    pipeline.df["ticker"] = pd.Series(pipeline.df["ticker"].tolist(), dtype="object")
    captured = {}

    def capture_core_frame(df):
        captured["ticker_dtype"] = str(df["ticker"].dtype)
        captured["ticker_storage"] = getattr(df["ticker"].dtype, "storage", None)
        return True

    with patch("ams.validators.cb_data_validator.CBDataValidator") as validator_cls:
        validator_cls.return_value.validate_dataframe.side_effect = capture_core_frame
        assert pipeline.run_stage_f_validator() is True

    report = pipeline.get_final_report()
    assert captured["ticker_dtype"] == "string"
    assert captured["ticker_storage"] == "pyarrow"
    assert report["validator_summary"]["status"] == "PASS"
    assert report["validator_summary"]["failure_type"] == "NONE"
    assert report["validator_summary"]["core_validator_status"] == "PASS"
    validator_text = " ".join(
        str(report["validator_summary"].get(key, ""))
        for key in ("message", "core_validator_message")
    )
    assert "expected series 'ticker' to have type string[pyarrow], got object" not in validator_text


def test_core_validator_input_normalization_preserves_numeric_and_bool_contracts():
    df_core = pd.DataFrame(
        {
            "ticker": pd.Series(["110001.XSHG", "110002.XSHG", pd.NA], dtype="object"),
            "date": [pd.Timestamp("2025-01-06")] * 3,
            "close": pd.Series(["100.5", "not-a-number", 101], dtype="object"),
            "is_st": pd.Series([True, False, True], dtype="object"),
            "is_redeemed": pd.Series([False, False, True], dtype="object"),
        }
    )

    normalized = _normalize_core_validator_input(df_core)

    assert str(normalized["ticker"].dtype) == "string"
    assert getattr(normalized["ticker"].dtype, "storage", None) == "pyarrow"
    assert is_numeric_dtype(normalized["close"])
    assert normalized["close"].iloc[0] == 100.5
    assert pd.isna(normalized["close"].iloc[1])
    assert is_bool_dtype(normalized["is_st"])
    assert is_bool_dtype(normalized["is_redeemed"])

    nullable_bool_core = df_core.copy()
    nullable_bool_core["is_redeemed"] = pd.Series([False, pd.NA, True], dtype="object")
    normalized_nullable = _normalize_core_validator_input(nullable_bool_core)
    assert normalized_nullable["is_redeemed"].dtype == nullable_bool_core["is_redeemed"].dtype
    assert pd.isna(normalized_nullable["is_redeemed"].iloc[1])

    valid_core = pd.DataFrame(
        {
            "ticker": pd.Series(["110001.XSHG", "110002.XSHG"], dtype="object"),
            "date": [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-06")],
            "close": pd.Series(["100.5", "101.0"], dtype="object"),
            "is_st": pd.Series([False, True], dtype="object"),
            "is_redeemed": pd.Series([False, False], dtype="object"),
        }
    )
    assert CBDataValidator().validate_dataframe(_normalize_core_validator_input(valid_core)) is True


def test_stage_f_does_not_run_legacy_dataset_thresholds_for_small_audit_window():
    pipeline = _contract_valid_pipeline()

    with patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as legacy_validator:
        assert pipeline.run_stage_f_validator() is True

    legacy_validator.assert_not_called()
    report = pipeline.get_final_report()
    assert report["validator_summary"]["status"] == "PASS"
    assert report["validator_summary"]["failure_type"] == "NONE"
    assert report["validator_summary"]["core_validator_status"] == "PASS"
    assert report["validator_summary"]["enrichment_validator_status"] == "PASS"
    assert "row_count" not in report["validator_summary"]["message"]
    assert report["root_blockers"] == []
