import pandas as pd

from etl.cb_etl_pipeline import CBETLPipeline


def test_supportability_failure_propagates_to_core_path_status():
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=None)
    pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["supportability_summary"].update(
        {
            "status": "FAIL",
            "failure_type": "SUPPORTABILITY_REGRESSION",
            "message": "Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO",
            "supportable_row_count": 1,
            "supportable_unique_bond_count": 1,
            "missing_underlying_row_count": 1,
            "missing_underlying_unique_bond_count": 1,
        }
    )
    pipeline.results["premium_join_summary"].update({"status": "NOT_RUN", "failure_type": "NONE", "message": ""})
    pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["validator_summary"].update(
        {
            "status": "NOT_RUN",
            "failure_type": "NONE",
            "message": "",
            "core_validator_status": "NOT_RUN",
            "core_validator_message": "",
            "enrichment_validator_status": "NOT_RUN",
            "enrichment_validator_message": "",
        }
    )
    pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "is_st": [False],
            "is_redeemed": [False],
        }
    )

    report = pipeline.get_final_report()

    assert report["core_path_status"] == "FAIL"
    assert report["validator_summary"]["promotion_gate_status"] == "BLOCKED"
    assert report["validator_summary"]["promotion_gate_message"] == "Promotion blocked: core_path_status != PASS"
    assert "SUPPORTABILITY_REGRESSION" in [item["type"] for item in report["root_blockers"]]


def test_redemption_failure_propagates_to_core_path_status_and_blocks_promotion():
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=None)
    pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["supportability_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "supportable_row_count": 1,
            "supportable_unique_bond_count": 1,
        }
    )
    pipeline.results["premium_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["redemption_summary"].update(
        {
            "status": "FAIL",
            "failure_type": "REDEMPTION_SOURCE_GAP",
            "message": "Redemption source contract regression: missing primary field delist_Date in bond.CONBOND_BASIC_INFO",
            "missing_redemption_ratio": 1.0,
        }
    )
    pipeline.results["validator_summary"].update(
        {
            "status": "NOT_RUN",
            "failure_type": "NONE",
            "message": "",
            "core_validator_status": "NOT_RUN",
            "core_validator_message": "",
            "enrichment_validator_status": "NOT_RUN",
            "enrichment_validator_message": "",
        }
    )
    pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
        }
    )

    report = pipeline.get_final_report()

    assert report["core_path_status"] == "FAIL"
    assert report["validator_summary"]["promotion_gate_status"] == "BLOCKED"
    assert report["validator_summary"]["promotion_gate_message"] == "Promotion blocked: core_path_status != PASS"
    assert "REDEMPTION_SOURCE_GAP" in [item["type"] for item in report["root_blockers"]]
