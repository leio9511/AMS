import pandas as pd
from unittest.mock import MagicMock, patch

from etl.cb_provider_base import DataProviderAuthError
from etl.cb_audit_contract import JQDATA_CONVERT_PRICE_PROVENANCE
from etl.cb_etl_pipeline import (
    CBETLPipeline,
    STAGE_STATUS_DEGRADED,
    PROMOTION_STATUS_BLOCKED,
    SUPPORTABILITY_BUCKET_SUPPORTABLE,
)
from etl.cb_etl_runner import run_etl

EXPECTED_TOP_LEVEL_KEYS = {
    "execution_mode",
    "start_date",
    "end_date",
    "final_status",
    "core_path_status",
    "enrichment_path_status",
    "non_promotion_disclaimer",
    "active_universe_summary",
    "source_coverage",
    "supportability_summary",
    "premium_join_summary",
    "is_st_join_summary",
    "redemption_summary",
    "validator_summary",
    "issue_1218_witness",
    "root_blockers",
    "secondary_findings",
}

EXPECTED_ACTIVE_UNIVERSE_SUMMARY_KEYS = {
    "core_price_row_count_before_filter",
    "core_price_row_count_after_filter",
    "all_null_ohlcv_row_count_filtered",
    "core_universe_row_count",
    "core_universe_unique_bond_count",
    "active_bond_universe_count",
    "enrichment_target_row_count",
    "enrichment_target_unique_bond_count",
}

EXPECTED_SOURCE_COVERAGE_KEYS = {
    "status",
    "failure_type",
    "message",
    "basic_info_row_count",
    "all_bond_security_count",
    "price_row_count",
    "price_unique_bond_count",
    "premium_source_row_count",
    "premium_source_unique_bond_count",
    "is_st_source_row_count",
    "is_st_source_unique_underlying_count",
    "redemption_source_row_count",
    "redemption_source_unique_bond_count",
}

EXPECTED_SUPPORTABILITY_SUMMARY_KEYS = {
    "status",
    "failure_type",
    "message",
    "supportable_row_count",
    "supportable_unique_bond_count",
    "outside_basic_info_row_count",
    "outside_basic_info_unique_bond_count",
    "missing_company_code_legacy_row_count",
    "missing_company_code_legacy_unique_bond_count",
    "unexpected_contract_regression_row_count",
    "unexpected_contract_regression_unique_bond_count",
    "missing_underlying_row_count",
    "missing_underlying_unique_bond_count",
}

EXPECTED_PREMIUM_JOIN_SUMMARY_KEYS = {
    "status",
    "failure_type",
    "message",
    "premium_joined_row_count",
    "premium_joined_unique_bond_count",
    "missing_premium_row_count",
    "missing_premium_unique_bond_count",
    "missing_premium_ratio",
    "premium_missing_ratio_against_active_universe",
    "rate_limited_enrichment",
    "permission_degraded_enrichment",
}

EXPECTED_IS_ST_JOIN_SUMMARY_KEYS = {
    "status",
    "failure_type",
    "message",
    "is_st_joined_row_count",
    "is_st_joined_unique_bond_count",
    "missing_is_st_row_count",
    "missing_is_st_unique_bond_count",
    "missing_is_st_ratio",
}

EXPECTED_REDEMPTION_SUMMARY_KEYS = {
    "status",
    "failure_type",
    "message",
    "redemption_joined_row_count",
    "redemption_joined_unique_bond_count",
    "missing_redemption_row_count",
    "missing_redemption_unique_bond_count",
    "missing_redemption_ratio",
}

EXPECTED_VALIDATOR_SUMMARY_KEYS = {
    "status",
    "failure_type",
    "message",
    "core_validator_status",
    "core_validator_message",
    "enrichment_validator_status",
    "enrichment_validator_message",
    "promotion_gate_status",
    "promotion_gate_message",
}

EXPECTED_ISSUE_1218_WITNESS_KEYS = {
    "issue_key",
    "old_signatures_absent",
    "signature_a",
    "signature_b",
}

EXPECTED_ROOT_BLOCKER_TYPES = {
    "SOURCE_AUTH_FAILURE",
    "PRICE_SOURCE_UNREADABLE",
    "SUPPORTABILITY_REGRESSION",
    "PREMIUM_SOURCE_TRUNCATION",
    "PREMIUM_RATE_MISSING_BROAD_COVERAGE",
    "RATE_LIMITED_ENRICHMENT",
    "PERMISSION_DEGRADED_ENRICHMENT",
    "IS_ST_SOURCE_GAP",
    "REDEMPTION_SOURCE_GAP",
    "VALIDATOR_SCHEMA_FAILURE",
    "VALIDATOR_SEMANTIC_FAILURE",
    "CONCURRENT_RUN_BLOCKED",
}
EXPECTED_ROOT_BLOCKER_STAGES = {"A", "B", "C", "D", "E", "F", "ORCH"}
EXPECTED_SECONDARY_FINDING_TYPES = {
    "MISSING_PREMIUM_RATE_ROWS",
    "MISSING_REDEMPTION_ROWS",
    "MISSING_IS_ST_ROWS",
    "MISSING_UNDERLYING_TICKER_ROWS",
    "EXCLUSION_ONLY_WINDOW",
}
EXPECTED_SECONDARY_FINDING_STAGES = {"B", "C", "D", "E"}


class _AuditProvider:
    def fetch_cb_basic(self):
        return pd.DataFrame({
            "code": ["110001.XSHG", "110002.XSHG"],
            "company_code": ["600001.XSHG", "600002.XSHG"],
            "delist_Date": [None, None],
        })

    def fetch_all_securities(self, types=None):
        return pd.DataFrame(index=["110001.XSHG", "110002.XSHG"])

    def fetch_cb_daily(self, tickers, start_date, end_date):
        return pd.DataFrame(
            {
                "time": ["2025-01-06", "2025-01-06"],
                "code": ["110001.XSHG", "110002.XSHG"],
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1200],
            }
        ).set_index(["code", "time"])

    def fetch_cb_price_changes(self, tickers, start_date, end_date):
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-01-06")],
                "code": ["110001.XSHG"],
                "convert_premium_rate": [10.0],
            }
        )

    def fetch_stock_st_by_date(self, tickers, start_date, end_date):
        return pd.DataFrame(
            {"600001.XSHG": [False], "600002.XSHG": [False]},
            index=pd.to_datetime(["2025-01-06"]),
        )

    def fetch_trade_calendar(self, start_date, end_date):
        return []


def _build_pipeline():
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=_AuditProvider())
    assert pipeline.run_stage_a_source_acquisition() is True
    assert pipeline.run_stage_b_supportability_classification() is True
    pipeline.run_stage_c_premium_join()
    pipeline.run_stage_d_is_st_join()
    pipeline.run_stage_e_redemption_delist()
    pipeline.run_stage_f_validator()
    return pipeline


def test_audit_schema_matches_exact_keys():
    pipeline = _build_pipeline()
    report = pipeline.get_final_report()

    assert set(report.keys()) == EXPECTED_TOP_LEVEL_KEYS
    assert set(report["active_universe_summary"].keys()) == EXPECTED_ACTIVE_UNIVERSE_SUMMARY_KEYS
    assert set(report["source_coverage"].keys()) == EXPECTED_SOURCE_COVERAGE_KEYS
    assert set(report["supportability_summary"].keys()) == EXPECTED_SUPPORTABILITY_SUMMARY_KEYS
    assert set(report["premium_join_summary"].keys()) == EXPECTED_PREMIUM_JOIN_SUMMARY_KEYS
    assert set(report["is_st_join_summary"].keys()) == EXPECTED_IS_ST_JOIN_SUMMARY_KEYS
    assert set(report["redemption_summary"].keys()) == EXPECTED_REDEMPTION_SUMMARY_KEYS
    assert set(report["validator_summary"].keys()) == EXPECTED_VALIDATOR_SUMMARY_KEYS
    assert set(report["issue_1218_witness"].keys()) == EXPECTED_ISSUE_1218_WITNESS_KEYS


def test_root_blockers_and_secondary_findings_use_exact_item_schema():
    pipeline = _build_pipeline()
    pipeline.results["supportability_summary"]["missing_underlying_row_count"] = 1
    pipeline.results["premium_join_summary"]["missing_premium_row_count"] = 1
    pipeline.results["premium_join_summary"]["failure_type"] = "PREMIUM_RATE_MISSING_BROAD_COVERAGE"
    pipeline.results["is_st_join_summary"]["missing_is_st_row_count"] = 1
    pipeline.results["redemption_summary"]["missing_redemption_row_count"] = 1
    pipeline.results["validator_summary"]["failure_type"] = "VALIDATOR_SCHEMA_FAILURE"
    pipeline.results["validator_summary"]["core_validator_message"] = "schema mismatch"

    root_blockers, secondary_findings = pipeline.compute_findings()

    assert root_blockers
    assert secondary_findings
    for item in root_blockers:
        assert set(item.keys()) == {"type", "stage", "trigger", "evidence"}
        assert item["type"] in EXPECTED_ROOT_BLOCKER_TYPES
        assert item["stage"] in EXPECTED_ROOT_BLOCKER_STAGES
    for item in secondary_findings:
        assert set(item.keys()) == {"type", "stage", "trigger", "evidence"}
        assert item["type"] in EXPECTED_SECONDARY_FINDING_TYPES
        assert item["stage"] in EXPECTED_SECONDARY_FINDING_STAGES


def test_audit_schema_defaults_survive_skipped_or_degraded_paths():
    skipped_pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    skipped_pipeline.df = pd.DataFrame(
        {
            "ticker": pd.Series(dtype="object"),
            "date": pd.Series(dtype="datetime64[ns]"),
            "bond_code_raw": pd.Series(dtype="object"),
            "bond_exchange_code": pd.Series(dtype="object"),
            "supportability_bucket": pd.Series(dtype="object"),
            "underlying_ticker": pd.Series(dtype="object"),
        }
    )
    skipped_pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    skipped_pipeline.results["supportability_summary"].update({"status": "PASS", "failure_type": "NONE", "message": "", "supportable_row_count": 0})
    skipped_pipeline.run_stage_c_premium_join()
    skipped_pipeline.run_stage_d_is_st_join()
    skipped_pipeline.run_stage_e_redemption_delist()
    skipped_pipeline.run_stage_f_validator()

    skipped_report = skipped_pipeline.get_final_report()

    assert skipped_report["premium_join_summary"]["status"] == "NOT_RUN"
    assert skipped_report["is_st_join_summary"]["status"] == "NOT_RUN"
    assert skipped_report["redemption_summary"]["status"] == "NOT_RUN"
    assert skipped_report["validator_summary"]["status"] == "PASS"
    assert set(skipped_report["premium_join_summary"].keys()) == EXPECTED_PREMIUM_JOIN_SUMMARY_KEYS
    assert set(skipped_report["is_st_join_summary"].keys()) == EXPECTED_IS_ST_JOIN_SUMMARY_KEYS
    assert set(skipped_report["redemption_summary"].keys()) == EXPECTED_REDEMPTION_SUMMARY_KEYS
    assert set(skipped_report["validator_summary"].keys()) == EXPECTED_VALIDATOR_SUMMARY_KEYS

    degraded_pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    degraded_pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "bond_code_raw": ["110001"],
            "bond_exchange_code": ["XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": ["600001.XSHG"],
            "is_st": [False],
            "is_redeemed": [False],
        }
    )
    degraded_pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    degraded_pipeline.results["supportability_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "supportable_row_count": 1,
            "supportable_unique_bond_count": 1,
        }
    )
    degraded_pipeline.results["active_universe_summary"].update(
        {
            "core_universe_row_count": 1,
            "core_universe_unique_bond_count": 1,
            "active_bond_universe_count": 1,
            "enrichment_target_row_count": 1,
            "enrichment_target_unique_bond_count": 1,
        }
    )

    with patch.object(CBETLPipeline, "_fetch_premium_batched", side_effect=RuntimeError("RATE_LIMITED_ENRICHMENT")):
        degraded_pipeline.run_stage_c_premium_join()
    degraded_pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    degraded_pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    degraded_pipeline.run_stage_f_validator()

    degraded_report = degraded_pipeline.get_final_report()

    assert degraded_report["premium_join_summary"]["status"] == "DEGRADED"
    assert degraded_report["premium_join_summary"]["failure_type"] == "RATE_LIMITED_ENRICHMENT"
    assert set(degraded_report["premium_join_summary"].keys()) == EXPECTED_PREMIUM_JOIN_SUMMARY_KEYS
    assert set(degraded_report["validator_summary"].keys()) == EXPECTED_VALIDATOR_SUMMARY_KEYS
    assert degraded_report["premium_join_summary"]["permission_degraded_enrichment"] is False


def test_promotion_gate_blocked_by_premium_missing():
    pipeline = _build_pipeline()
    report = pipeline.get_final_report()

    assert report["active_universe_summary"]["enrichment_target_row_count"] == 2
    assert report["premium_join_summary"]["premium_missing_ratio_against_active_universe"] == 0.5
    assert report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert report["core_path_status"] == "PASS"
    assert "premium_missing_ratio_against_active_universe > 0.05" in report["validator_summary"]["promotion_gate_message"]


def test_validator_summary_uses_prd_semantics_without_legacy_dataset_drift_failures():
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
            "redeem_risk": [False, False],
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
            "core_universe_row_count": 2,
            "core_universe_unique_bond_count": 2,
            "active_bond_universe_count": 2,
            "enrichment_target_row_count": 2,
            "enrichment_target_unique_bond_count": 2,
        }
    )

    with patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as legacy_validator:
        assert pipeline.run_stage_f_validator() is True

    legacy_validator.assert_not_called()
    report = pipeline.get_final_report()
    assert report["validator_summary"]["status"] == "PASS"
    assert report["validator_summary"]["failure_type"] == "NONE"
    assert report["validator_summary"]["core_validator_status"] == "PASS"
    assert report["validator_summary"]["core_validator_message"] == ""
    assert report["validator_summary"]["enrichment_validator_status"] == "PASS"
    assert "row_count" not in report["validator_summary"]["message"]
    assert "drift" not in report["validator_summary"]["message"].lower()
    assert report["root_blockers"] == []


def test_audit_core_pass_with_enrichment_degraded():
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "bond_code_raw": ["110001"],
            "bond_exchange_code": ["XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": ["600001.XSHG"],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
        }
    )
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
    pipeline.results["active_universe_summary"].update(
        {
            "core_universe_row_count": 1,
            "core_universe_unique_bond_count": 1,
            "active_bond_universe_count": 1,
            "enrichment_target_row_count": 1,
            "enrichment_target_unique_bond_count": 1,
        }
    )

    with patch.object(CBETLPipeline, "_fetch_premium_batched", side_effect=RuntimeError("RATE_LIMITED_ENRICHMENT")):
        pipeline.run_stage_c_premium_join()
    pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.run_stage_f_validator()

    report = pipeline.get_final_report()
    assert report["core_path_status"] == "PASS"
    assert report["enrichment_path_status"] == STAGE_STATUS_DEGRADED
    assert report["premium_join_summary"]["status"] == STAGE_STATUS_DEGRADED
    assert report["validator_summary"]["core_validator_status"] == "PASS"
    assert report["validator_summary"]["enrichment_validator_status"] == STAGE_STATUS_DEGRADED
    assert report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert report["premium_join_summary"]["rate_limited_enrichment"] is True


def test_promotion_gate_blocked_when_double_low_or_permission_contract_is_missing():
    missing_double_low_pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    missing_double_low_pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "premium_rate": [0.10],
            "bond_code_raw": ["110001"],
            "bond_exchange_code": ["XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": ["600001.XSHG"],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
        }
    )
    missing_double_low_pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    missing_double_low_pipeline.results["supportability_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "supportable_row_count": 1,
            "supportable_unique_bond_count": 1,
        }
    )
    missing_double_low_pipeline.results["premium_join_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "premium_joined_row_count": 1,
            "premium_joined_unique_bond_count": 1,
            "missing_premium_row_count": 0,
            "missing_premium_unique_bond_count": 0,
            "missing_premium_ratio": 0.0,
            "premium_missing_ratio_against_active_universe": 0.0,
            "rate_limited_enrichment": False,
            "permission_degraded_enrichment": False,
        }
    )
    missing_double_low_pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    missing_double_low_pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    missing_double_low_pipeline.results["active_universe_summary"].update(
        {
            "core_universe_row_count": 1,
            "core_universe_unique_bond_count": 1,
            "active_bond_universe_count": 1,
            "enrichment_target_row_count": 1,
            "enrichment_target_unique_bond_count": 1,
        }
    )

    missing_double_low_pipeline.run_stage_f_validator()
    missing_double_low_report = missing_double_low_pipeline.get_final_report()

    assert missing_double_low_report["core_path_status"] == "PASS"
    assert missing_double_low_report["validator_summary"]["core_validator_status"] == "PASS"
    assert missing_double_low_report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert missing_double_low_report["validator_summary"]["promotion_gate_message"] == "Promotion blocked: double_low column is missing"

    permission_degraded_pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    permission_degraded_pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "bond_code_raw": ["110001"],
            "bond_exchange_code": ["XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": ["600001.XSHG"],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
        }
    )
    permission_degraded_pipeline.results["source_coverage"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    permission_degraded_pipeline.results["supportability_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "supportable_row_count": 1,
            "supportable_unique_bond_count": 1,
        }
    )
    permission_degraded_pipeline.results["active_universe_summary"].update(
        {
            "core_universe_row_count": 1,
            "core_universe_unique_bond_count": 1,
            "active_bond_universe_count": 1,
            "enrichment_target_row_count": 1,
            "enrichment_target_unique_bond_count": 1,
        }
    )

    with patch.object(permission_degraded_pipeline.provider, "fetch_cb_price_changes", side_effect=DataProviderAuthError("permission denied")):
        permission_degraded_pipeline.run_stage_c_premium_join()
    permission_degraded_pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    permission_degraded_pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    permission_degraded_pipeline.run_stage_f_validator()

    permission_degraded_report = permission_degraded_pipeline.get_final_report()

    assert permission_degraded_report["core_path_status"] == "PASS"
    assert permission_degraded_report["enrichment_path_status"] == STAGE_STATUS_DEGRADED
    assert permission_degraded_report["premium_join_summary"]["status"] == STAGE_STATUS_DEGRADED
    assert permission_degraded_report["premium_join_summary"]["failure_type"] == "PERMISSION_DEGRADED_ENRICHMENT"
    assert permission_degraded_report["premium_join_summary"]["permission_degraded_enrichment"] is True
    assert permission_degraded_report["validator_summary"]["core_validator_status"] == "PASS"
    assert permission_degraded_report["validator_summary"]["enrichment_validator_status"] == STAGE_STATUS_DEGRADED
    assert permission_degraded_report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert permission_degraded_report["validator_summary"]["promotion_gate_message"] == "Promotion blocked: permission_degraded_enrichment == true"


def test_concurrent_run_blocked_reports_only_orch_blocker():
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "bond_code_raw": ["110001"],
            "bond_exchange_code": ["XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": ["600001.XSHG"],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
        }
    )
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
    pipeline.results["active_universe_summary"].update(
        {
            "core_universe_row_count": 1,
            "core_universe_unique_bond_count": 1,
            "active_bond_universe_count": 1,
            "enrichment_target_row_count": 1,
            "enrichment_target_unique_bond_count": 1,
        }
    )

    with patch.object(CBETLPipeline, "_fetch_premium_batched", side_effect=RuntimeError("CONCURRENT_RUN_BLOCKED")):
        pipeline.run_stage_c_premium_join()
    pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.run_stage_f_validator()

    report = pipeline.get_final_report()

    assert set(report["premium_join_summary"].keys()) == EXPECTED_PREMIUM_JOIN_SUMMARY_KEYS
    assert set(report["validator_summary"].keys()) == EXPECTED_VALIDATOR_SUMMARY_KEYS
    assert report["premium_join_summary"]["status"] == "FAIL"
    assert report["premium_join_summary"]["failure_type"] == "NONE"
    assert report["premium_join_summary"]["message"] == "CONCURRENT_RUN_BLOCKED"
    assert report["validator_summary"]["failure_type"] == "NONE"
    assert report["validator_summary"]["status"] == "PASS"
    blocker_types = [item["type"] for item in report["root_blockers"]]
    assert blocker_types == ["CONCURRENT_RUN_BLOCKED"]
    assert all(item["type"] != "VALIDATOR_SCHEMA_FAILURE" for item in report["root_blockers"])


def test_core_path_is_not_masked_when_supportability_stage_fails():
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=MagicMock())
    pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": [pd.Timestamp("2025-01-06")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "bond_code_raw": ["110001"],
            "bond_exchange_code": ["XSHG"],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": [None],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
        }
    )
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
            "unexpected_contract_regression_row_count": 0,
            "unexpected_contract_regression_unique_bond_count": 0,
        }
    )
    pipeline.results["premium_join_summary"].update(
        {
            "status": "DEGRADED",
            "failure_type": "RATE_LIMITED_ENRICHMENT",
            "message": "TuShare cb_price_chg rate limit hit",
            "premium_missing_ratio_against_active_universe": 1.0,
            "rate_limited_enrichment": True,
            "permission_degraded_enrichment": False,
        }
    )
    pipeline.results["is_st_join_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["redemption_summary"].update({"status": "PASS", "failure_type": "NONE", "message": ""})
    pipeline.results["validator_summary"].update(
        {
            "status": "PASS",
            "failure_type": "NONE",
            "message": "",
            "core_validator_status": "PASS",
            "core_validator_message": "",
            "enrichment_validator_status": STAGE_STATUS_DEGRADED,
            "enrichment_validator_message": "High missing ratio on premium: 100.00%",
        }
    )

    report = pipeline.get_final_report()

    assert report["core_path_status"] == "FAIL"
    assert report["enrichment_path_status"] == STAGE_STATUS_DEGRADED
    assert report["supportability_summary"]["failure_type"] == "SUPPORTABILITY_REGRESSION"
    assert report["premium_join_summary"]["failure_type"] == "RATE_LIMITED_ENRICHMENT"
    assert report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert report["validator_summary"]["promotion_gate_message"] == "Promotion blocked: core_path_status != PASS"
    blocker_types = [item["type"] for item in report["root_blockers"]]
    assert "SUPPORTABILITY_REGRESSION" in blocker_types
    assert "RATE_LIMITED_ENRICHMENT" in blocker_types


def test_pipeline_rejects_tushare_convert_price_without_provenance_instead_of_stamping_jqdata():
    class _TuShareLikePremiumProvider(_AuditProvider):
        pass

    provider = _TuShareLikePremiumProvider()
    with patch.object(
        provider,
        "fetch_cb_price_changes",
        return_value=pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-01-06")],
                "code": ["110001.XSHG"],
                "convert_price": [10.0],
                "convert_premium_rate": [10.0],
            }
        ),
    ):
        pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=provider)
        assert pipeline.run_stage_a_source_acquisition() is True
        assert pipeline.run_stage_b_supportability_classification() is True
        assert pipeline.run_stage_c_premium_join() is False

    summary = pipeline.results["premium_join_summary"]
    assert summary["status"] == "FAIL"
    assert "convert_price_provenance is required" in summary["message"]
    assert JQDATA_CONVERT_PRICE_PROVENANCE not in summary["message"]
    assert "convert_price_provenance" not in pipeline.df.columns or not (
        pipeline.df["convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE
    ).any()


def test_run_etl_promotion_gate_blocks_promotion(tmp_path):
    dataset_path = tmp_path / "cb.csv"
    metrics_path = tmp_path / "cb.metrics.json"

    mock_pipeline = MagicMock()
    mock_pipeline.run_stage_a_source_acquisition.return_value = True
    mock_pipeline.run_stage_b_supportability_classification.return_value = True
    mock_pipeline.run_stage_c_premium_join.return_value = False
    mock_pipeline.run_stage_d_is_st_join.return_value = True
    mock_pipeline.run_stage_e_redemption_delist.return_value = True
    mock_pipeline.run_stage_f_validator.return_value = False
    mock_pipeline.df = pd.DataFrame(
        {
            "ticker": ["110001.XSHG"],
            "date": ["2025-01-06"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "premium_rate": [None],
            "double_low": [None],
            "underlying_ticker": ["600001.XSHG"],
            "is_st": [False],
            "redeem_risk": [False],
            "is_redeemed": [False],
            "supportability_bucket": ["supportable"],
            "bond_code_raw": ["110001"],
        }
    )
    mock_pipeline.results = {
        "source_coverage": {"premium_source_row_count": 0},
        "premium_join_summary": {"premium_joined_row_count": 0, "missing_premium_ratio": 1.0},
        "redemption_summary": {"missing_redemption_row_count": 0},
        "validator_summary": {"promotion_gate_status": "BLOCKED", "promotion_gate_message": "Promotion blocked: premium_rate column is missing"},
    }
    mock_pipeline.get_final_report.return_value = {
        "validator_summary": {"promotion_gate_status": "BLOCKED", "promotion_gate_message": "Promotion blocked: premium_rate column is missing"}
    }

    with patch("etl.cb_etl_runner.load_provider_config", return_value={"providers": {"jqdata": {"dataset_path": str(dataset_path), "metrics_path": str(metrics_path)}}}), \
         patch("etl.cb_etl_runner.get_provider"), \
         patch("etl.cb_etl_runner.CBETLPipeline", return_value=mock_pipeline):
        try:
            run_etl("2025-01-06", "2025-01-06", "jqdata", promote=True, dataset_path=str(dataset_path), metrics_path=str(metrics_path))
            assert False, "expected SystemExit"
        except SystemExit as exc:
            assert exc.code == 1

    assert not dataset_path.exists()
    assert not metrics_path.exists()
    assert not (tmp_path / "cb.csv.tmp").exists()
    assert not (tmp_path / "cb.csv.bak").exists()
    assert not (tmp_path / "cb.metrics.json.tmp").exists()
    assert not (tmp_path / "cb.metrics.json.bak").exists()
