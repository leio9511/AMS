import pandas as pd
from unittest.mock import MagicMock, patch

from etl.cb_etl_pipeline import (
    CBETLPipeline,
    STAGE_STATUS_DEGRADED,
    PROMOTION_STATUS_BLOCKED,
    SUPPORTABILITY_BUCKET_SUPPORTABLE,
)
from etl.cb_etl_runner import run_etl


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

    assert set(report.keys()) == {
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
        "root_blockers",
        "secondary_findings",
    }
    assert set(report["validator_summary"].keys()) == {
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


def test_promotion_gate_blocked_by_premium_missing():
    pipeline = _build_pipeline()
    report = pipeline.get_final_report()

    assert report["active_universe_summary"]["enrichment_target_row_count"] == 2
    assert report["premium_join_summary"]["premium_missing_ratio_against_active_universe"] == 0.5
    assert report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert report["core_path_status"] == "PASS"
    assert "premium_missing_ratio_against_active_universe > 0.05" in report["validator_summary"]["promotion_gate_message"]


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
    assert report["validator_summary"]["promotion_gate_status"] == PROMOTION_STATUS_BLOCKED
    assert report["premium_join_summary"]["rate_limited_enrichment"] is True


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
