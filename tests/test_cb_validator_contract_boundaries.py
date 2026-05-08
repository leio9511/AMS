import pandas as pd
from unittest.mock import MagicMock, patch

from etl.cb_etl_pipeline import CBETLPipeline, SUPPORTABILITY_BUCKET_SUPPORTABLE


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


def test_stage_f_still_does_not_invoke_legacy_semantic_validator_after_path_cutover():
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


def test_stage_f_normalizes_ticker_dtype_before_validator_contract_check():
    pipeline = _contract_valid_pipeline()
    pipeline.df["ticker"] = pipeline.df["ticker"].astype(object)

    assert pipeline.run_stage_f_validator() is True

    summary = pipeline.results["validator_summary"]
    assert summary["core_validator_status"] == "PASS"
    assert "expected series 'ticker' to have type string[pyarrow], got object" not in summary["core_validator_message"]


def test_stage_f_normalizes_ticker_dtype_before_core_schema_validation():
    pipeline = _contract_valid_pipeline()
    pipeline.df["ticker"] = pd.Series(["110001.XSHG", "110002.XSHG"], dtype=object)

    assert pipeline.run_stage_f_validator() is True

    summary = pipeline.results["validator_summary"]
    assert summary["core_validator_status"] == "PASS"
    assert summary["status"] == "PASS"
    assert "expected series 'ticker' to have type string[pyarrow], got object" not in summary["core_validator_message"]


def test_stage_f_normalization_does_not_mask_real_core_contract_failures():
    pipeline = _contract_valid_pipeline()
    pipeline.df["ticker"] = pd.Series([None, "110002.XSHG"], dtype=object)
    pipeline.df["close"] = ["100.5", "not-a-number"]
    pipeline.df["is_st"] = [False, "bad-bool"]

    assert pipeline.run_stage_f_validator() is False

    summary = pipeline.results["validator_summary"]
    assert summary["core_validator_status"] == "FAIL"
    assert summary["failure_type"] == "VALIDATOR_SCHEMA_FAILURE"
    assert summary["status"] == "FAIL"
    assert "Schema" in summary["message"] or "schema" in summary["core_validator_message"]



def test_stage_f_validator_allows_is_st_gap_without_erasing_stage_d_gap_witness():
    pipeline = _contract_valid_pipeline()
    pipeline.df["is_st"] = [False, None]
    pipeline.results["is_st_join_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "Observed source coverage gap for is_st but within tolerance.",
            "missing_is_st_row_count": 1,
            "missing_is_st_ratio": 0.5,
        }
    )

    assert pipeline.run_stage_f_validator() is True

    summary = pipeline.results["validator_summary"]
    assert summary["core_validator_status"] == "PASS"
    assert "non-nullable series 'is_st' contains null values:" not in summary["core_validator_message"]

    report = pipeline.get_final_report()
    assert report["is_st_join_summary"]["missing_is_st_row_count"] == 1
    assert report["is_st_join_summary"]["missing_is_st_ratio"] == 0.5



def test_stage_f_normalization_does_not_mask_invalid_is_st_non_boolean_values():
    pipeline = _contract_valid_pipeline()
    pipeline.df["is_st"] = [False, "bad-bool"]

    assert pipeline.run_stage_f_validator() is False

    summary = pipeline.results["validator_summary"]
    assert summary["core_validator_status"] == "FAIL"
    assert summary["failure_type"] == "VALIDATOR_SCHEMA_FAILURE"
    assert summary["status"] == "FAIL"
    assert "is_st" in summary["core_validator_message"]
